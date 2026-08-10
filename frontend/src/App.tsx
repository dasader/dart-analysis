import { Routes, Route } from "react-router-dom";
import Layout from "./components/Layout";
import CompanyList from "./pages/CompanyList";
import CompanyDetail from "./pages/CompanyDetail";
import ReportDetail from "./pages/ReportDetail";
import BatchList from "./pages/BatchList";
import PromptSettings from "./pages/PromptSettings";
import TagSettings from "./pages/TagSettings";

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route path="/" element={<CompanyList />} />
        <Route path="/companies/:id" element={<CompanyDetail />} />
        <Route path="/companies/:id/reports/:reportId" element={<ReportDetail />} />
        <Route path="/settings/prompts" element={<PromptSettings />} />
        <Route path="/settings/batches" element={<BatchList />} />
        <Route path="/tags" element={<TagSettings />} />
      </Route>
    </Routes>
  );
}
