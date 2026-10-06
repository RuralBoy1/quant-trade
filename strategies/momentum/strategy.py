from math import sqrt

import backtrader as bt
from backtest import EventLog


# 时间序列动量突破法
class MomentumStrategy(bt.Strategy):
    params = {
        ("mom_window", 90),  # 动量回看窗口
        ("vol_window", 30),  # 波动率估计窗口
        ("target_vol", 0.40),  # 目标年华波动率
        ("rebal_tol", 0.25),  # 再平衡阈值，超过该值才调仓
        ("verbose", False)
    }

    def __init__(self):
        # 指标计算
        # 日收益率
        self.pct = bt.indicators.PercentChange(self.data.close, period=1)
        # 日波动率
        self.ret_vol = bt.indicators.StdDev(self.pct, period=self.p.vol_window)

        self.pending = None
        self.target_pct = None
        self.exit_reason = None

        # ---------- 统计与日志 ----------
        self.stat_filled = 0
        self.stat_buys = 0
        self.stat_sells = 0
        self.stat_margin = 0
        self.stat_dead = 0
        self.stat_comm = 0.0
        self.events = EventLog(verbose=self.p.verbose)

        self._warmup = max(self.p.mom_window, self.p.vol_window) + 1

    def _vol_annual(self) -> float:
        """ 已实现的年化  波动率 """
        return self.ret_vol[0] * sqrt(365)

    def log(self, txt, force=False, **fields):
        """记录一条事件日志（verbose 只控制打印，结构化字段永远记下来）。"""
        self.events.add(self.data.datetime.date(0), txt, force=force, **fields)

    def next(self):
        if len(self.data) < self._warmup:
            return

        if self.pending is not None:
            return

        price = self.data.close[0]
        # 计算动量信号
        mom = price / self.data.close[-self.p.mom_window] - 1.0

        if not self.position:
            if mom <= 0:
                return

            w = min(self.p.target_vol / self._vol_annual(), 1.0)
            self.target_pct = w
            order = self.buy()
            order.order_role = 'entry'
            self.pending = order

            self.log(
                f"开仓信号 close={price:.2f} "
                f"动量={mom:.2f} "
                f"目标波动率={self.target_pct:.2f} "
                f"qty={order.created.size:.8g} "
                f"equity={self.broker.getvalue():.3f}",
                event="开仓信号",
                close=price,
                mom=mom,
                target_pct=self.target_pct,
                qty=order.created.size,
                estimatedCash=self.broker.getcash(),
                equity=self.broker.getvalue(),
            )
        else:
            # ---- TODO 2：三个分支，注意优先级 ----
            #   a) 清仓（动量转负）：mom <= 0
            #      self.exit_reason = "MOMENTUM_TURN"；先 log event="退出信号"，再 self.pending = self.close()
            if mom <= 0:
                self.exit_reason = "MOMENTUM_TURN"
                self.pending = self.close()
                self.log(
                    f"退出信号 reason={self.exit_reason} "
                    f"close={price:.2f} "
                    f"动量={mom:.2f} ",
                    event="退出信号",
                    reason=self.exit_reason,
                    close=price,
                    mom=mom,
                    position=self.position.size,
                )
                #   b) 再平衡（动量仍为正，但权重跑偏了）：
                #      当前权重 cur = self.position.size * price / self.broker.getvalue()
                #      新目标 w = min(target_vol / vol_annual(), 1.0)
                #      偏离判断：用相对偏离 abs(cur - w) / w > rebal_tol（w 会变，所以每根都要算）
                #      触发后：self.target_pct = w；log event="再平衡信号"（字段含 curPct/targetPct/reason="REBAL"）
                #              self.pending = self.order_target_percent(target=w)
                #      思考题：order_target_percent 会走 sizer 吗？（跑一次把 sizer 里加 print 就知道了，
                #             答案写在 TODO.md 的自查清单里）
                #   c) 其余情况不动 —— 不动就是 alpha，动量策略换手率高一点，手续费会吃掉很多收益
            else:
                cur = self.position.size * price / self.broker.getvalue()
                w = min(self.p.target_vol / self._vol_annual(), 1.0)
                if abs(cur - w) / w > self.p.rebal_tol:
                    self.target_pct = w
                    self.exit_reason = "REBAL"
                    self.pending = self.order_target_percent(target=w)
                    self.log(
                        f"再平衡信号 reason={self.exit_reason} "
                        f"close={price:.2f} "
                        f"cur={cur:.2f}"
                        f"权重={w:.2f} ",
                        event="再平衡信号",
                        reason=self.exit_reason,
                        close=price,
                        cur=cur,
                        w=self.target_pct,
                        position=self.position.size,
                    )


    def notify_order(self, order):
        if order.status in (order.Submitted, order.Accepted):
            return

        self.pending = None

        if order.status == order.Completed:
            ex = order.executed
            self.stat_filled += 1
            self.stat_comm += ex.comm

            if order.isbuy():
                self.stat_buys += 1
                self.log(
                    f"买入成交 size={ex.size:+.8g} price={float(ex.price):.2f} "
                    f"targetPct={self.target_pct:.3f}",
                    event="买入成交",
                    role=getattr(order, "order_role", ""),
                    fill=float(ex.price),
                    qty=ex.size,
                    targetPct=self.target_pct,
                    avgPrice=self.position.price,
                    position=self.position.size,
                    equity=self.broker.getvalue(),
                )
            else:
                self.stat_sells += 1
                self.log(
                    f"卖出成交 reason={self.exit_reason} size={ex.size:+.8g} "
                    f"price={float(ex.price):.2f} position={self.position.size:+.8g}",
                    event="卖出成交",
                    reason=self.exit_reason,
                    closedSize=abs(ex.size),
                    barOpen=float(self.data.open[0]),
                    position=self.position.size,
                    equity=self.broker.getvalue(),
                    buyFills=self.stat_buys,
                    sellFills=self.stat_sells,
                )

                # ---- TODO 3：复位条件（这里是和 turtle 最大的不同）----
                # turtle 的每一次卖出都是"清仓"，所以无条件复位全部状态。
                # momentum 的卖出有两种：再平衡的部分减仓（REBAL）、动量转负的清仓。
                # 问：什么时候才该把 self.exit_reason / self.target_pct 复位？
                #     在部分减仓后复位，会导致什么 bug？（提示：看 log 里 reason 会不会串）
                if self.exit_reason == "MOMENTUM_TURN":
                    self.exit_reason = None
                    self.target_pct = None
                if self.position.size == 0:
                    self.exit_reason = None
                    self.target_pct = 0.0
            return

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
