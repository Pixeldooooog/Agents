/** Keep the original failure available while giving users a useful next action. */
export function describeFailure(detail: string): {
  title: string;
  hint: string;
} {
  if (/\b(401|403)\b|unauthorized|forbidden/i.test(detail))
    return {
      title: "连接需要重新确认",
      hint: "请在设置中检查访问令牌和模型密钥，再试一次。",
    };
  if (/\b429\b|rate.limit|quota/i.test(detail))
    return {
      title: "服务暂时有些忙",
      hint: "可能达到请求频率或额度限制。稍后重试，或检查模型服务的额度。",
    };
  if (/timeout|timed.out/i.test(detail))
    return {
      title: "等待的时间有些长",
      hint: "本次请求没有及时完成。检查连接后，可以重新发送。",
    };
  if (
    /ECONN|fetch failed|failed to fetch|network|load failed|socket/i.test(
      detail,
    )
  )
    return {
      title: "连接中断了",
      hint: "检查本地服务与网络连接，恢复后再试一次。",
    };
  return {
    title: "这一步没有完成",
    hint: "可以查看具体原因，调整后重新尝试。",
  };
}
