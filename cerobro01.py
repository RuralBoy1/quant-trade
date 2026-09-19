from tkinter.font import names

import backtrader as bt

def main():
   cerebro =  bt.Cerebro();
   print(f"账号初始化资金{cerebro.broker.getvalue()}");
   # 设置资金
   cerebro.broker.setcash(10000);
   # 设置交易佣金
   cerebro.broker.setcommission(commission=0.0005);
   # 设置滑点
   cerebro.broker.set_slippage_fixed(fixed=0.001);
   cerebro.run();
   print(f"账户最终资金{cerebro.broker.getvalue()}");
   # 添加数据
   data = bt.feeds.GenericCSVData(dataname = './datas/orcl-1995-2014.txt' , dtformat='%Y-%m-%d');
   cerebro.adddata(data);
   cerebro.run();
   cerebro.plot(style='candlestick');


if __name__ == '__main__':
   main()
