import backtrader as bt


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
        self.stat_margin = 0
        self.stat_dead = 0
        self.stat_comm = 0.0

    def log(self, txt):
        print(f"{self.data.datetime.date(0)} {txt}")

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
        atr = self.atr[0]

        # 没有仓位：突破 20 日高点开仓（size 由 TurtleSize 决定）
        if not self.position:
            if current_price > entry_up:
                self.pending = self.buy()
        # 有仓位
        else:
            # 加仓：每上涨 0.5N 加一个单位
            if (self.last_entry_price is not None
                    and current_price >= self.last_entry_price + 0.5 * atr
                    and self.unit_count < 4):
                self.pending = self.buy()
            else:
                # 出场：反向 2 个 ATR 止损，或跌破 10 日最低。
                # 必须合成一个平仓分支，否则同一根 K 线出两次 close() 会把仓位打成反向
                stop_loss = (self.last_entry_price is not None
                             and current_price < self.last_entry_price - 2 * atr)
                if stop_loss or current_price < exit_down:
                    self.pending = self.close()

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
                # 用真实成交价记账：成交发生在"下一根 bar 的开盘"，
                # 而不是发出信号那根 bar 的收盘价，跳空时两者差别很大
                self.unit_count += 1
                self.last_entry_price = ex.price
            else:
                self.unit_count = 0
                self.last_entry_price = None

            if self.p.verbose:
                self.log(f"成交 {'买入' if order.isbuy() else '卖出'} "
                         f"{ex.size:+.8g}@{ex.price:.2f} "
                         f"手续费={ex.comm:.2f} 持仓={self.position.size:+.8g}")
            return

        # 以下都是“没能成交”，必须处理，否则就是静默丢单
        if order.status == order.Margin:
            self.stat_margin += 1
            self.log(f"！！资金不足被拒 ref={order.ref} "
                     f"想下={order.created.size:.8g} "
                     f"现金={self.broker.getcash():.2f} "
                     f"权益={self.broker.getvalue():.2f}")
        elif order.status in (order.Canceled, order.Expired):
            self.stat_dead += 1
            if self.p.verbose:
                self.log(f"订单失效 ref={order.ref} {order.getstatusname()}")
        elif order.status == order.Rejected:
            self.stat_dead += 1
            self.log(f"！！订单被拒 ref={order.ref}")

    def stop(self):
        print(f"[订单统计] 成交={self.stat_filled} 笔  "
              f"资金不足拒单={self.stat_margin} 笔  "
              f"失效/被拒={self.stat_dead} 笔  "
              f"手续费合计={self.stat_comm:.2f}  "
              f"最终权益={self.broker.getvalue():.2f}")
