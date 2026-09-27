from strategy.turtule_trade import TurtleStrategy
from strategy.turtle_size import TurtleSize
import pandas as pd

import backtrader as bt

# 加载数据
data = bt.feeds.PandasData(
    dataname=pd.read_csv('./datas/BTCUSDT_1d.csv', index_col=0, parse_dates=True)
)
cerebro = bt.Cerebro()
cerebro.adddata(data)
cerebro.addstrategy(TurtleStrategy, verbose=True)
# 仓位管理器必须注册到 cerebro，sizer 才会拿到 strategy / broker 引用
cerebro.addsizer(TurtleSize)

# 设置初始资金、手续费
cerebro.broker.setcash(100000)
cerebro.broker.setcommission(0.001)

print(f'Starting Value: {cerebro.broker.getvalue():.2f}')
cerebro.run()
print(f'Final Value:    {cerebro.broker.getvalue():.2f}')

cerebro.plot()
