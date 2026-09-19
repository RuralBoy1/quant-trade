import sys
import time

import yfinance as yf
import backtrader as bt


class BuyHold(bt.Strategy):
    def next(self):
        if not self.position:
            self.buy()


def download(ticker: str, start: str, end: str, max_retries: int = 5) -> "object":
    """下载数据，限流/网络瞬时错误会自动重试（指数退避）。"""
    last_err: Exception | None = None
    for attempt in range(max_retries):
        try:
            data = yf.download(
                ticker,
                start=start,
                end=end,
                multi_level_index=False,
                progress=False,
            )
            if data.empty:
                raise RuntimeError("empty dataframe returned")
            return data
        except Exception as e:  # YFRateLimitError 等瞬时错误
            last_err = e
            wait = 2 ** (attempt + 1)
            if attempt < max_retries - 1:
                print(f"[retry {attempt + 1}/{max_retries}] 下载失败: {e}，{wait}s 后重试", file=sys.stderr)
                time.sleep(wait)
    raise last_err


def main() -> None:
    try:
        raw_data = download("AAPL", "2020-01-01", "2021-01-01")
    except Exception as e:
        print(f"下载数据失败: {e}", file=sys.stderr)
        sys.exit(1)

    data = bt.feeds.PandasData(dataname=raw_data.dropna())

    cerebro = bt.Cerebro()
    cerebro.addstrategy(BuyHold)
    cerebro.adddata(data)
    cerebro.broker.setcash(1e8)
    print(f"初始资金: {cerebro.broker.getcash()}")
    cerebro.run()
    print(f"最终资金: {cerebro.broker.getcash()}")

    if data.buflen() == 0:
        print("没有可用的行情数据（可能仍被限流），跳过绘图。", file=sys.stderr)
        sys.exit(1)

    cerebro.plot()


if __name__ == "__main__":
    main()
