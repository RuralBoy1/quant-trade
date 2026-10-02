import backtrader as bt


class TurtleSize(bt.Sizer):
    # 注意：单元素 params 元组也必须带逗号，否则会被当成 ("risk_per_trade", 0.01)
    # 这样一个二元组，backtrader 解析时抛 ValueError: too many values to unpack
    params = (
        ("risk_per_trade", 0.01),
        ("cash_buffer", 0.001),  # 给手续费和次日开盘跳空留缓冲
    )

    def _getsizing(self, comminfo, cash, data, isbuy):
        # 只在下单方向为买入时计算仓位（平仓走 close()，size 由框架给出）
        if not isbuy:
            # 卖出方向：返回当前持仓量 = "清仓"。
            # 注意是 getposition 不是 getpostion（拼错会在调用 sell() 时 AttributeError）
            return abs(self.strategy.getposition(data).size)

        atr = self.strategy.atr[0]
        if atr <= 0.0:
            return 0

        # 海龟法则：每笔风险 = 总资产 * risk_per_trade，1 个 N(ATR) 的波动对应这个风险
        total = self.broker.getvalue()
        size = (total * self.params.risk_per_trade) / atr

        # 现货不做杠杆，最多用当前可用现金能买到的数量
        price = data.close[0]
        # 购买一股需要的手续费和价格
        unit = (comminfo.getoperationcost(1.0, price)) + (comminfo.getcommission(1.0, price))
        if unit <= 0.0:
            return 0

        size = min(size, cash * (1 - self.params.cash_buffer) / unit)

        return round(size, 8)
