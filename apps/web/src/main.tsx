import { render } from "solid-js/web";
import { WorkCanvasPreview } from "./components/kevin/WorkCanvas";
import { DesignStudio } from "./components/kevin/DesignStudio";
import { OperationStagePreview } from "./components/kevin/OperationStagePreview";
import { App } from "./app/App";
import "./styles/index.css";

const design = new URLSearchParams(location.search).get("design");
render(() => design === "operations" ? <OperationStagePreview /> : design === "workspace" ? <WorkCanvasPreview /> : design !== null ? <DesignStudio /> : <App />, document.getElementById("root") as HTMLElement);
