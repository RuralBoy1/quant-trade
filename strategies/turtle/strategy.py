import backtrader as bt

from backtest.recorders import EventLog


class TurtleStrategy(bt.Strategy):
    params = (
        ("entry_window", 20),
        ("exit_window", 10),
        ("atr_window", 20),
        ("risk_per_trade", 0.01),
        # 是否逐笔打印订单日志。资金不足/被拒这类异常不受此开关影响，永远打印
        ("verbose", False),
    )

    def __init__(self):
        # 计算 ATR(N)
        self.atr = bt.indicators.ATR(self.data, period=self.params.atr_window)
        # 加仓次数(最多加仓4次)
        self.unit_count = 0
        # 最后一次买入的**实际成交价**（由 notify_order 写入）
        self.last_entry_price = None
        # 在途订单。不为 None 时不再下新单，避免同一时间挂出多张
        self.pending = None
        # 订单统计
        self.stat_filled = 0
        # 上一笔订单成交使用的atr
        self.last_entry_n = None
        # 下一加仓触发价格
        self.next_add_price = None
        # 全仓止损价
        self.stop_price = None
        self.stat_margin = 0
        self.stat_dead = 0
        self.stat_comm = 0.0
        # 结构化日志。事件名与字段名对齐 TradingView 的 pine-logs，方便逐字段对比
        self.events = EventLog(verbose=self.p.verbose)
        self.stat_buys = 0
        self.stat_sells = 0
        # 退出原因，在 next() 决定平仓时写入，卖出成交时记录
        self.exit_reason = None

    def log(self, txt, force=False, **fields):
        """记录一条事件日志。

        verbose 只控制打不打印，结构化字段总是记下来，
        这样安静模式跑完也能导出完整日志做对比。txt 供人阅读，fields 供机器对比。
        """
        self.events.add(self.data.datetime.date(0), txt, force=force, **fields)

    def next(self):
        # 指标与窗口预热，避免越界取值
        warmup = max(self.params.entry_window, self.params.atr_window) + 1
        if len(self.data) < warmup:
            return

        # 有订单在途就不动（市价单通常下一根 bar 就会了结，此处主要防限价单）
        if self.pending is not None:
            return

        # ago=-1 表示取“不包含当前 bar”的最近 N 根
        entry_up = max(self.data.high.get(size=self.params.entry_window, ago=-1))
        exit_down = min(self.data.low.get(size=self.params.exit_window, ago=-1))
        current_price = self.data.close[0]

        # 没有仓位：突破 20 日高点开仓（size 由 TurtleSize 决定）
        if not self.position:
            if current_price > entry_up:
                order = self.buy()
                order.entry_n = float(self.atr[0])
                order.order_role = 'initial_entry'
                self.pending = order
                self.log(
                    f"开仓信号 close={current_price:.2f} "
                    f"entryUp={entry_up:.2f} "
                    f"N={float(self.atr[0]):.2f} "
                    f"qty={order.created.size:.8g} "
                    f"equity={self.broker.getvalue():.3f}",
                    event="开仓信号",
                    close=current_price,
                    entryUp=entry_up,
                    N=float(self.atr[0]),
                    qty=order.created.size,
                    estimatedCash=self.broker.getcash(),
                    equity=self.broker.getvalue(),
                )
        # 有仓位
        else:
            # 加仓
            add_signal = (self.unit_count < 4 and
                          self.next_add_price is not None and
                          current_price >= self.next_add_price)

            stop_signal = (
                    self.stop_price is not None and
                    current_price <= self.stop_price
            )

            channel_exit = current_price <= exit_down

            if stop_signal or channel_exit:
                if stop_signal and channel_exit:
                    reason = "STOP_AND_CHANNEL"
                elif stop_signal:
                    reason = "STOP"
                else:
                    reason = "CHANNEL"
                # notify_order 里卖出成交时要用，所以不放在 verbose 分支内
                self.exit_reason = reason

                self.log(
                    f"退出信号 reason={reason} "
                    f"close={current_price:.2f} "
                    f"stop={self.stop_price:.2f} "
                    f"exit_down={exit_down:.2f} "
                    f"units={self.unit_count}",
                    event="退出信号",
                    reason=reason,
                    close=current_price,
                    stop=self.stop_price,
                    exitDown=exit_down,
                    position=self.position.size,
                    units=self.unit_count,
                )

                self.pending = self.close()

            elif add_signal:
                order = self.buy()
                order.entry_n = float(self.atr[0])
                order.order_role = 'add_entry'
                self.pending = order
                self.log(
                    f"加仓信号 close={current_price:.2f} "
                    f"trigger={self.next_add_price:.2f} "
                    f"current_N={float(self.atr[0]):.2f} "
                    f"units={self.unit_count}",
                    event="加仓信号",
                    close=current_price,
                    trigger=self.next_add_price,
                    N=float(self.atr[0]),
                    qty=order.created.size,
                    units=self.unit_count,
                    stop=self.stop_price,
                )

    def notify_order(self, order):
        # 中间态：订单已提交/已被接受，还没有结果，直接忽略。
        # 注意市价单也会先后收到这两次回调，所以必须按 status 过滤，
        # 否则一张单会被当成多次成交重复记账。
        if order.status in (order.Submitted, order.Accepted):
            return

        # 走到这里说明是终态，这张单结束了，放行下一张
        self.pending = None

        if order.status == order.Completed:
            ex = order.executed
            self.stat_filled += 1
            self.stat_comm += ex.comm

            if order.isbuy():
                fill_price = float(ex.price)
                # 第一次买入的atr
                fill_n = float(order.entry_n)
                self.unit_count += 1
                self.stat_buys += 1
                self.last_entry_price = fill_price
                self.last_entry_n = fill_n
                # 上升0.5N加仓一次
                self.next_add_price = fill_price + 0.5 * fill_n
                # 本次成交对应的候选止损
                candidate_stop = fill_price - 2.0 * fill_n
                if self.stop_price is None:
                    self.stop_price = candidate_stop
                else:
                    # 加仓后的止损向上移动
                    self.stop_price = max(candidate_stop, self.stop_price)


                role = 'INITIAL' if getattr(order, 'order_role', '') == 'initial_entry' else 'ADD'
                self.log(
                    f"买入成交 role={role} "
                    f"size={ex.size:+.8g} "
                    f"price={fill_price:.2f} "
                    f"N={fill_n:.2f} "
                    f"units={self.unit_count} "
                    f"next_add={self.next_add_price:.2f} "
                    f"stop={self.stop_price:.2f}",
                    event="买入成交",
                    role=role,
                    addedSize=ex.size,
                    fill=fill_price,
                    N=fill_n,
                    units=self.unit_count,
                    nextAdd=self.next_add_price,
                    stop=self.stop_price,
                    avgPrice=self.position.price,
                    equity=self.broker.getvalue(),
                )
            else:
                self.stat_sells += 1
                self.log(
                    f"卖出成交 reason={self.exit_reason} "
                    f"size={ex.size:+.8g} "
                    f"barOpen={self.data.open[0]:.2f} "
                    f"price={ex.price:.2f} "
                    f"commission={ex.comm:.2f} "
                    f"position={self.position.size:+.8g}",
                    event="卖出成交",
                    reason=self.exit_reason,
                    closedSize=abs(ex.size),
                    barOpen=float(self.data.open[0]),
                    equity=self.broker.getvalue(),
                    buyFills=self.stat_buys,
                    sellFills=self.stat_sells,
                )

                self.exit_reason = None
                self.unit_count = 0
                self.last_entry_price = None
                self.last_entry_n = None
                self.next_add_price = None
                self.stop_price = None
            return

        # 以下都是“没能成交”，必须处理，否则就是静默丢单。
        # 这些事件 Pine 侧没有对应记录，导出后会以“仅 Backtrader”出现在对比表里
        if order.status == order.Margin:
            self.stat_margin += 1
            self.log(f"！！资金不足被拒 ref={order.ref} "
                     f"想下={order.created.size:.8g} "
                     f"现金={self.broker.getcash():.2f} "
                     f"权益={self.broker.getvalue():.2f}",
                     force=True,
                     event="资金不足被拒",
                     size=order.created.size,
                     cash=self.broker.getcash(),
                     equity=self.broker.getvalue())
        elif order.status in (order.Canceled, order.Expired):
            self.stat_dead += 1
            self.log(f"订单失效 ref={order.ref} {order.getstatusname()}",
                     event="订单失效",
                     status=order.getstatusname())
        elif order.status == order.Rejected:
            self.stat_dead += 1
            self.log(f"！！订单被拒 ref={order.ref}",
                     force=True,
                     event="订单被拒",
                     size=order.created.size)

    def stop(self):
        # Pine 日志末尾也有一条同样的状态，用来核对回测结束时的持仓
        self.events.record(
            self.data.datetime.date(0),
            event="到达本地数据末尾",
            close=float(self.data.close[0]),
            position=self.position.size,
            avgPrice=self.position.price,
            units=self.unit_count,
            equity=self.broker.getvalue(),
        )
        print(f"[订单统计] 成交={self.stat_filled} 笔  "
              f"资金不足拒单={self.stat_margin} 笔  "
              f"失效/被拒={self.stat_dead} 笔  "
              f"手续费合计={self.stat_comm:.2f}  "
              f"最终权益={self.broker.getvalue():.2f}")
