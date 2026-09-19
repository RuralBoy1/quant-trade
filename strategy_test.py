import backtrader as bt


class TestStrategy(bt.Strategy):
    def __init__(self):
        self.dataclose = self.datas[0].close
        self.bar_execute = 0
        self.order = None

    def log(self, txt, dt=None):
        dt = dt or self.datetime.date(0)
        print("%s, %s " % (dt.isoformat(), txt))

    def notify_order(self, order):
        self.log(f"Order status , {bt.Order.Status[order.status]}")
        if order.status == bt.Order.Completed:
            # 成交价格
            self.log(f"excute price , {order.executed.price}")
            # 成交金额
            self.log(f"execute value , {order.executed.value}")
            # 手续费
            self.log(f"execute commision , {order.executed.comm}")
            if order.isbuy():
                self.bar_execute = len(self)
        if order.status not in [bt.Order.Submitted, bt.Order.Accepted, bt.Order.Created, bt.Order.Partial]:
            self.order = None

    def next(self):
        self.log("Close , %.2f" % self.dataclose[0])
        if self.order:
            return
        if not self.position:
            if self.dataclose[0] < self.dataclose[-1] < self.dataclose[-2]:
                self.order = self.buy()
                self.log(f"BUY CREATE, %.2f" % self.dataclose[0])
        else:
            if len(self) > self.bar_execute + 5:
                self.order = self.sell()
                self.log(f"SELL CREATE, %.2f" % self.dataclose[0])


def main():
    cerebro = bt.Cerebro();
    cerebro.broker.setcash(1e6);
    cerebro.broker.setcommission(commission=0.0005);
    print(f"账号初始化资金{cerebro.broker.getvalue()}");

    data = bt.feeds.GenericCSVData(dataname='./datas/orcl-1995-2014.txt', dtformat='%Y-%m-%d');
    cerebro.adddata(data)
    cerebro.addstrategy(TestStrategy);
    cerebro.run();
    cerebro.plot();
    print(f"账户最终资金{cerebro.broker.getvalue()}");


if __name__ == '__main__':
    main()
