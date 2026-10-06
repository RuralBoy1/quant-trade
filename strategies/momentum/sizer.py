import backtrader as bt


class MomentTumtSize(bt.Sizer):
    """波动率目标仓位：把"仓位权重"换算成币数。

    和另外两个 sizer 的区别：
        TurtleSize   用 ATR 反推风险敞口，支持加仓
        FixedFractionSize  固定权益比例，不随波动率变化
        VolTargetSize      权重由策略算好（self.strategy.target_pct），sizer 只做换算
                           —— 这是"目标权重"类策略的标准分工：
                              strategy 决定"买多少比例"，sizer 决定"比例对应几个币"
    """

    params = (
        ("cash_buffer", 0.005),  # 成交在下一根开盘，留缓冲应对跳空与手续费
    )

    def _getsizing(self, comminfo, cash, data, isbuy):
        # 平仓方向走 self.close()，框架自己会给 size；这里只在买入时算量
        if not isbuy:
            return abs(self.strategy.getposition(data).size)

        # ---- TODO：按目标权重算币数 ----
        # 1) 权重从策略拿：w = getattr(self.strategy, "target_pct", 0.0)
        #    w <= 0 时直接 return 0（防御：不该出现的信号别让它下成空单/负单）
        w = getattr(self.strategy, "target_pct", 0.0)
        if w <= 0:
            return 0

        # 2) 目标金额 = w × self.broker.getvalue()（用总权益，不是现金）
        # 3) 换算成币数：参考 TurtleSize 的两行写法——
        #       unit = comminfo.getoperationcost(1.0, price) + comminfo.getcommission(1.0, price)
        #       size = 目标金额 / unit
        #    注意 price 用什么：成交在下一根开盘，用 data.close[0] 会略微低估成本，
        #    所以才要 cash_buffer。想更严格可以 × (1 + cash_buffer) 再算，自己权衡。
        price = data.close[0]
        unit = comminfo.getoperationcost(1.0, price) + comminfo.getcommission(1.0, price)

        # 4) 现货约束：size 再被 cash × (1 - cash_buffer) / unit 夹一次（不能透支）
        size = min(w * self.broker.getvalue(), cash * (1 - self.params.cash_buffer)) / unit
        # 5) return round(size, 8)
        return round(size, 8)
