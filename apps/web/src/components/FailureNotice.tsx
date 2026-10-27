import { AlertCircle } from "lucide-solid";
import { describeFailure } from "../runtime/failurePresentation";

export function FailureNotice(props: { detail: string }) {
  const failure = () => describeFailure(props.detail);
  return (
    <div class="failure-notice" role="alert">
      <AlertCircle size={18} />
      <div>
        <strong>{failure().title}</strong>
        <p>{failure().hint}</p>
        <details>
          <summary>查看具体原因</summary>
          <pre>{props.detail}</pre>
        </details>
      </div>
    </div>
  );
}
