import { Routes, Route } from "react-router-dom";
import Layout from "./components/Layout";
import CompanyList from "./pages/CompanyList";
import CompanyDetail from "./pages/CompanyDetail";
import PromptSettings from "./pages/PromptSettings";
import TagSettings from "./pages/TagSettings";

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route path="/" element={<CompanyList />} />
        <Route path="/companies/:id" element={<CompanyDetail />} />
        <Route path="/settings/prompts" element={<PromptSettings />} />
        <Route path="/tags" element={<TagSettings />} />
      </Route>
    </Routes>
  );
}
