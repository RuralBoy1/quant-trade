import backtrader as bt
from backtest.recorders import EventLog


class MeanRevStrategy(bt.Strategy):
    params = {
        ("bb_window", 20),  # 布林带中轨的移动平均周期
        ("bb_K", 2.0),  # 上下轨的标准倍数差
        ("trend_window", 200),  # 长期趋势过滤的均线周期
        ("stop_pct", 0.08),  # 固定止损百分比
        ("stop_mode", "pct"),  # 止损方式
        ("atr_window", 20),  # atr窗口
        ("atr_mult", 2.0),  # atr止损距离
        ("exit_band", "mid"),  # 止盈目标，中轨
        ("time_stop_bars", 15),  # 时间止损的K线数量，持仓时间超过15根K线未回归止损
        ("cooldown_bars", 0),  # 冷却期，平仓后多少bar内禁止开仓
        ("require_bull" , False), # 当阳线才开仓
        ("verbose", False),
    }

    def __init__(self):
        self.bb = bt.indicators.BollingerBands(
            self.data.close, period=self.p.bb_window, devfactor=self.p.bb_K
        )
        # 上轨
        self.top = self.bb.lines.top
        # 中轨
        self.mid = self.bb.lines.mid
        # 下轨
        self.bot = self.bb.lines.bot
        # 长期趋势
        self.trend = bt.indicators.SMA(self.data.close, period=self.p.trend_window)
        # ATR止损使用
        self.atr = bt.indicators.ATR(self.data, period=self.p.atr_window)

        # 运行时状态
        self.pending = None  # 在途订单
        self.entry_price = None  # 实际成交价
        self.entry_bar = None  # 入场时的bar数量，len（data）
        self.last_exit_bar = None
        self.stop_price = None
        self.exit_reason = None
        # 结构化与统计日志
        self.stat_filled = 0
        self.stat_buys = 0
        self.stat_sells = 0
        self.stat_margin = 0
        self.stat_dead = 0
        self.stat_comm = 0.0
        self.events = EventLog(verbose=self.p.verbose)
        # 数据预热
        self._warmup = max(self.p.bb_window, self.p.trend_window, self.p.atr_window) + 1

    def log(self, txt, force=False, **fields):
        """记录一条事件日志。

        verbose 只控制打不打印，结构化字段总是记下来，
        这样安静模式跑完也能导出完整日志做对比。txt 供人阅读，fields 供机器对比。
        """
        self.events.add(self.data.datetime.date(0), txt, force=force, **fields)

    def next(self):
        if len(self.data) < self._warmup:
            return
        if self.pending is not None:
            return
        # 当前价格
        price = self.data.close[0]

        if not self.position:
            # 冷却期：距上次清仓不足 cooldown_bars 根就不开仓
            cooled = (self.last_exit_bar is None
                      or len(self.data) - self.last_exit_bar >= self.p.cooldown_bars)

            if self.p.require_bull:
                bull = price > self.data.open[0]
            else:
                bull = True
            if price <= self.bot[-1] and price >= self.trend[0] and cooled and bull:
                order = self.buy()
                order.order_role = 'initial_entry'
                self.pending = order
                self.log(
                    f"开仓信号 close={price:.2f} "
                    f"下轨={self.bot[-1]:.2f} "
                    f"中轨={self.mid[-1]:.2f} "
                    f"qty={order.created.size:.8g} "
                    f"equity={self.broker.getvalue():.3f}",
                    event="开仓信号",
                    close=price,
                    bot=self.bot[-1],
                    mid=self.mid[-1],
                    qty=order.created.size,
                    estimatedCash=self.broker.getcash(),
                    equity=self.broker.getvalue(),
                )
        else:
            # 止盈目标：默认中轨，exit_band="top" 时改为上轨
            target = self.top[-1] if self.p.exit_band == "top" else self.mid[-1]
            # 价格回到目标轨平仓
            midband = price >= target
            # 止损价格
            stop = price <= self.stop_price
            # 持仓超过固定bar
            time = len(self.data) - self.entry_bar >= self.p.time_stop_bars

            if midband or stop or time:
                if midband:
                    reason = "MIDBAND"
                elif stop:
                    reason = "STOP"
                else:
                    reason = "TIME"
                # notify_order 里卖出成交时要用，所以不放在 verbose 分支内
                self.exit_reason = reason

                self.log(
                    f"退出信号 reason={reason} "
                    f"close={price:.2f} "
                    f"stop={self.stop_price:.2f}",
                    event="退出信号",
                    reason=reason,
                    close=price,
                    stop=self.stop_price,
                    position=self.position.size,
                )

                self.pending = self.close()

    def notify_order(self, order):
        if order.status in (order.Submitted, order.Accepted):
            return

        self.pending = None

        if order.status == order.Completed:
            self.stat_filled += 1
            self.stat_comm += order.executed.comm
            ex = order.executed
            fill_price = ex.price

            if order.isbuy():
                self.stat_buys += 1
                self.entry_price = fill_price
                # ---- TODO 3：两行状态维护 ----
                self.entry_bar = len(self.data)
                # a) 记录入场 bar：self.entry_bar = len(self.data)
                #    （想一下为什么是 len(self.data) 而不是 len(self.data) - 1：成交发生在哪根 bar？）
                # b) 算硬止损价：per stop_pct
                if self.p.stop_mode == "atr":
                    self.stop_price = fill_price - self.p.atr_mult * self.atr[-1]
                else:
                    self.stop_price = fill_price * (1 - self.p.stop_pct)
                self.log(
                    f"买入成交 size={ex.size:+.8g} price={fill_price:.2f} "
                    f"stop={self.stop_price}",
                    event="买入成交",
                    role=getattr(order, "order_role", ""),
                    fill=fill_price,
                    stop=self.stop_price,
                    avgPrice=self.position.price,
                    equity=self.broker.getvalue(),
                )
            else:
                self.stat_sells += 1
                self.last_exit_bar = len(self.data)
                self.log(
                    f"卖出成交 reason={self.exit_reason} size={ex.size:+.8g} "
                    f"price={ex.price:.2f} commission={ex.comm:.2f}",
                    event="卖出成交",
                    reason=self.exit_reason,
                    closedSize=abs(ex.size),
                    barOpen=float(self.data.open[0]),
                    equity=self.broker.getvalue(),
                    buyFills=self.stat_buys,
                    sellFills=self.stat_sells,
                )
                # 清仓后把所有状态复位（沿用 turtle 的复位清单），漏一个下一轮就会算错
                self.exit_reason = None
                self.entry_price = None
                self.entry_bar = None
                self.stop_price = None
            return

        # 以下都是"没能成交"，必须处理，否则就是静默丢单
        if order.status == order.Margin:
            self.stat_margin += 1
            self.log(
                f"！！资金不足被拒 ref={order.ref} 想下={order.created.size:.8g} "
                f"现金={self.broker.getcash():.2f} 权益={self.broker.getvalue():.2f}",
                force=True,
                event="资金不足被拒",
                size=order.created.size,
                cash=self.broker.getcash(),
                equity=self.broker.getvalue(),
            )
        elif order.status in (order.Canceled, order.Expired, order.Rejected):
            self.stat_dead += 1
            self.log(
                f"订单失效/被拒 ref={order.ref} {order.getstatusname()}",
                force=True,
                event="订单失效",
                status=order.getstatusname(),
                size=order.created.size,
            )

    def stop(self):
        # 回测末尾留一条状态，用来核对结束时的持仓
        self.events.record(
            self.data.datetime.date(0),
            event="到达本地数据末尾",
            close=float(self.data.close[0]),
            position=self.position.size,
            avgPrice=self.position.price,
            equity=self.broker.getvalue(),
        )
        print(
            f"[订单统计] 成交={self.stat_filled} 笔  "
            f"资金不足拒单={self.stat_margin} 笔  "
            f"失效/被拒={self.stat_dead} 笔  "
            f"手续费合计={self.stat_comm:.2f}  "
            f"最终权益={self.broker.getvalue():.2f}"
        )
