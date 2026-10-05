import backtrader as bt


class MeanRevSize(bt.Sizer):
    # 固定权益比例仓位：每笔用 fraction × 总权益 建仓，不加仓。
    params = (
        ("fraction", 0.25),
        ("cash_buffer", 0.005),  # 成交在下一根开盘，留缓冲应对跳空与手续费
    )

    def _getsizing(self, comminfo, cash, data, isbuy):
        # 平仓方向：返回当前持仓量（= 清仓）。注意是 getposition，别拼错
        if not isbuy:
            return abs(self.strategy.getposition(data).size)

        # ---- TODO：算出买入数量 ----
        # 目标金额 = self.params.fraction × self.broker.getvalue()
        # 但现金是硬约束，所以要再被 cash × (1 - cash_buffer) 夹一次。
        #
        # "买 1 个币要花多少钱"参考 turtle/sizer.py 的写法：
        #     unit = comminfo.getoperationcost(1.0, price) + comminfo.getcommission(1.0, price)
        #
        # 思考：price 用 data.close[0] 还是别的？
        #   成交发生在下一根 bar 的开盘，用当根收盘价会低估成本（所以才要 cash_buffer）。
        #   如果你想让回测更严格，可以拿 data.close[0] × (1 + 0.005) 当保守估价，自己权衡。
        #
        # 最后 return round(size, 8)，别返回负数或 NaN。
        price = data.close[0]
        unit = comminfo.getoperationcost(1.0, price) + comminfo.getcommission(1.0, price)
        if unit <= 0.0:
            return 0
        target = self.broker.getvalue() * self.p.fraction
        size = min(target, cash * (1 - self.params.cash_buffer)) / unit
        return round(size, 8)
