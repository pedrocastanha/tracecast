import { BrowserRouter, Routes, Route } from "react-router-dom";
import { MOUNT_PREFIX } from "./base";
import { Layout } from "./components/Layout";
import { Overview } from "./pages/Overview";
import { Traces } from "./pages/Traces";
import { Models } from "./pages/Models";
import { Sessions } from "./pages/Sessions";
import { Projects } from "./pages/Projects";
import { TraceDetail } from "./pages/TraceDetail";
import { Evaluators } from "./pages/Evaluators";
import { EvalRunDetail } from "./pages/EvalRunDetail";
import { EvalCompare } from "./pages/EvalCompare";
import { Prompts } from "./pages/Prompts";

export function App() {
  return (
    <BrowserRouter basename={MOUNT_PREFIX || "/"}>
      <Routes>
        <Route element={<Layout />}>
          <Route path="/" element={<Overview />} />
          <Route path="/traces" element={<Traces />} />
          <Route path="/traces/:traceId" element={<TraceDetail />} />
          <Route path="/models" element={<Models />} />
          <Route path="/sessions" element={<Sessions />} />
          <Route path="/projects" element={<Projects />} />
          <Route path="/evals" element={<Evaluators />} />
          <Route path="/evals/compare" element={<EvalCompare />} />
          <Route path="/evals/:runId" element={<EvalRunDetail />} />
          <Route path="/prompts" element={<Prompts />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
