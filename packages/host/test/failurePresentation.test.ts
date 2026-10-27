import { expect, test } from "bun:test";
import { describeFailure } from "../../../apps/web/src/runtime/failurePresentation.js";

test("failure presentation preserves meaningful categories and avoids guessing unknown causes", () => {
  expect(describeFailure("stream request failed: 401 Unauthorized").title).toBe(
    "连接需要重新确认",
  );
  expect(describeFailure("provider 429 quota exceeded").title).toBe(
    "服务暂时有些忙",
  );
  expect(describeFailure("ECONNRESET: socket closed").title).toBe("连接中断了");
  expect(describeFailure("request timed out").title).toBe("等待的时间有些长");
  expect(describeFailure("invalid response schema").title).toBe(
    "这一步没有完成",
  );
});
