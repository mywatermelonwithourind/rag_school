"use client";

import {
  AlertTriangle,
  Boxes,
  Check,
  Database,
  Eye,
  FileText,
  Hash,
  Info,
  Layers,
  ListTree,
  Loader2,
  RefreshCw,
  Search,
  ScrollText,
  Trash2,
  UploadCloud,
  X,
} from "lucide-react";
import { ChangeEvent, DragEvent, ReactNode, useCallback, useEffect, useMemo, useRef, useState } from "react";

interface KbFileSummary {
  file_id: string;
  original_name: string;
  display_name: string;
  file_type: string;
  status: string;
  parent_count: number;
  child_count: number;
  character_count: number;
  ingested_at: string;
}

interface KbFileChild {
  child_chunk_id: string;
  chunk_index: number;
  content: string;
}

interface KbFileParent {
  parent_chunk_id: string;
  chunk_index: number;
  title: string;
  content: string;
  children: KbFileChild[];
}

interface KbFileDetail extends KbFileSummary {
  full_text: string;
  reconstruction_notice: string;
  parents: KbFileParent[];
}

interface IngestState {
  name: string;
  status: "processing" | "ready" | "error";
  message: string;
}

interface FileManagerProps {
  apiBase: string;
}

const ACCEPTED_TYPES = ".pdf,.docx,.txt,.md,application/pdf,text/plain,text/markdown,application/vnd.openxmlformats-officedocument.wordprocessingml.document";

function formatNumber(value: number) {
  return new Intl.NumberFormat("zh-CN").format(value);
}

function formatDate(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "时间未知";
  return new Intl.DateTimeFormat("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(date);
}

function responseError(data: unknown, fallback: string) {
  if (data && typeof data === "object" && "detail" in data && typeof data.detail === "string") {
    return data.detail;
  }
  return fallback;
}

function StatusBadge({ status }: { status: string }) {
  const ready = status === "ready";
  const failed = status === "failed";
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-md px-2 py-0.5 text-xs font-medium ${
        ready
          ? "bg-emerald-50 text-emerald-700"
          : failed
            ? "bg-rose-50 text-rose-700"
            : "bg-amber-50 text-amber-700"
      }`}
    >
      {ready && <Check className="h-3 w-3" />}
      {status}
    </span>
  );
}

function Stat({
  icon,
  label,
  value,
}: {
  icon: ReactNode;
  label: string;
  value: string;
}) {
  return (
    <div className="rounded-lg border border-slate-200 bg-white px-4 py-3">
      <div className="flex items-center gap-2 text-xs text-slate-500">
        {icon}
        {label}
      </div>
      <div className="mt-1 text-xl font-semibold tabular-nums text-slate-950">{value}</div>
    </div>
  );
}

function Modal({
  children,
  onClose,
  labelledBy,
}: {
  children: ReactNode;
  onClose: () => void;
  labelledBy: string;
}) {
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [onClose]);

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
      role="dialog"
      aria-modal="true"
      aria-labelledby={labelledBy}
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      {children}
    </div>
  );
}

function ViewFileModal({
  file,
  detail,
  loading,
  error,
  tab,
  onTabChange,
  onClose,
}: {
  file: KbFileSummary;
  detail: KbFileDetail | null;
  loading: boolean;
  error: string | null;
  tab: "full" | "structure";
  onTabChange: (tab: "full" | "structure") => void;
  onClose: () => void;
}) {
  return (
    <Modal onClose={onClose} labelledBy="file-view-title">
      <div className="flex max-h-[88vh] w-full max-w-3xl flex-col overflow-hidden rounded-lg bg-white shadow-2xl">
        <div className="flex items-start gap-3 border-b border-slate-200 px-5 py-4">
          <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-slate-100">
            <FileText className="h-4 w-4 text-slate-600" />
          </div>
          <div className="min-w-0 flex-1">
            <h2 id="file-view-title" className="truncate text-sm font-semibold text-slate-950">
              {file.display_name}
            </h2>
            <p className="mt-1 text-xs text-slate-500">
              {file.parent_count} 个父块 · {formatNumber(file.character_count)} 字符 · {formatDate(file.ingested_at)}
            </p>
          </div>
          <button type="button" onClick={onClose} className="rounded-lg p-2 text-slate-500 hover:bg-slate-100 hover:text-slate-900" aria-label="关闭查看窗口" title="关闭">
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="flex items-start gap-2 border-b border-amber-100 bg-amber-50 px-5 py-3 text-xs leading-5 text-amber-900">
          <Info className="mt-0.5 h-4 w-4 shrink-0" />
          <span>非原始文件，由父块按序拼接还原，内容完整但排版可能与原文件不同。</span>
        </div>

        <div className="flex gap-1 border-b border-slate-200 px-5 pt-2">
          <button type="button" onClick={() => onTabChange("full")} className={`inline-flex items-center gap-2 border-b-2 px-3 py-2 text-xs font-medium ${tab === "full" ? "border-slate-950 text-slate-950" : "border-transparent text-slate-500 hover:text-slate-900"}`}>
            <ScrollText className="h-4 w-4" />
            全文（拼接还原）
          </button>
          <button type="button" onClick={() => onTabChange("structure")} className={`inline-flex items-center gap-2 border-b-2 px-3 py-2 text-xs font-medium ${tab === "structure" ? "border-slate-950 text-slate-950" : "border-transparent text-slate-500 hover:text-slate-900"}`}>
            <ListTree className="h-4 w-4" />
            切片结构
          </button>
        </div>

        <div className="min-h-48 flex-1 overflow-y-auto px-5 py-4">
          {loading ? (
            <div className="flex min-h-48 items-center justify-center gap-2 text-sm text-slate-500">
              <Loader2 className="h-4 w-4 animate-spin" />
              正在读取父块
            </div>
          ) : error ? (
            <div className="rounded-lg border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">{error}</div>
          ) : detail && tab === "full" ? (
            <article className="whitespace-pre-wrap text-sm leading-7 text-slate-700">{detail.full_text}</article>
          ) : detail ? (
            <div className="divide-y divide-slate-200">
              {detail.parents.map((parent) => (
                <section key={parent.parent_chunk_id} className="py-4 first:pt-0">
                  <div className="flex flex-wrap items-center gap-2 text-xs font-medium text-slate-600">
                    <Layers className="h-4 w-4" />
                    父块 #{parent.chunk_index}
                    <span className="font-normal text-slate-400">{parent.parent_chunk_id}</span>
                  </div>
                  <p className="mt-2 whitespace-pre-wrap text-sm leading-7 text-slate-700">{parent.content}</p>
                  <div className="mt-3 border-l-2 border-slate-200 pl-3">
                    <p className="mb-2 flex items-center gap-2 text-xs font-medium text-slate-500">
                      <Boxes className="h-3.5 w-3.5" />
                      {parent.children.length} 个子块
                    </p>
                    <div className="space-y-2">
                      {parent.children.map((child) => (
                        <p key={child.child_chunk_id} className="bg-slate-50 px-3 py-2 text-xs leading-5 text-slate-600">
                          {child.content}
                        </p>
                      ))}
                    </div>
                  </div>
                </section>
              ))}
            </div>
          ) : null}
        </div>
      </div>
    </Modal>
  );
}

function DeleteFileModal({
  file,
  deleting,
  error,
  onCancel,
  onConfirm,
}: {
  file: KbFileSummary;
  deleting: boolean;
  error: string | null;
  onCancel: () => void;
  onConfirm: () => void;
}) {
  const close = deleting ? () => undefined : onCancel;
  return (
    <Modal onClose={close} labelledBy="file-delete-title">
      <div className="w-full max-w-md overflow-hidden rounded-lg bg-white shadow-2xl">
        <div className="px-5 py-5">
          <div className="flex h-10 w-10 items-center justify-center rounded-full bg-rose-50">
            <AlertTriangle className="h-5 w-5 text-rose-600" />
          </div>
          <h2 id="file-delete-title" className="mt-4 text-base font-semibold text-slate-950">确认一键出库？</h2>
          <p className="mt-1 break-words text-sm text-slate-500">{file.display_name}</p>
          <div className="mt-4 border-l-2 border-rose-300 bg-rose-50 px-3 py-3 text-xs leading-6 text-rose-900">
            此操作不可恢复，将同时删除 Milvus 中该文件的全部子块向量，以及父块库中的全部父块全文。
          </div>
          <div className="mt-3 grid grid-cols-2 gap-2 text-xs text-slate-600">
            <span className="flex items-center gap-2"><Database className="h-4 w-4" />{file.child_count} 个子块向量</span>
            <span className="flex items-center gap-2"><Layers className="h-4 w-4" />{file.parent_count} 个父块</span>
          </div>
          {error && <p className="mt-3 text-sm text-rose-700">{error}</p>}
        </div>
        <div className="flex gap-2 border-t border-slate-200 px-5 py-3">
          <button type="button" disabled={deleting} onClick={onCancel} className="flex-1 rounded-lg border border-slate-200 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-50">
            取消
          </button>
          <button type="button" disabled={deleting} onClick={onConfirm} className="flex flex-1 items-center justify-center gap-2 rounded-lg bg-rose-600 py-2 text-sm font-medium text-white hover:bg-rose-700 disabled:opacity-60">
            {deleting && <Loader2 className="h-4 w-4 animate-spin" />}
            {deleting ? "正在出库" : "确认出库"}
          </button>
        </div>
      </div>
    </Modal>
  );
}

export default function FileManager({ apiBase }: FileManagerProps) {
  const [files, setFiles] = useState<KbFileSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [dragOver, setDragOver] = useState(false);
  const [ingest, setIngest] = useState<IngestState | null>(null);
  const [viewing, setViewing] = useState<KbFileSummary | null>(null);
  const [detail, setDetail] = useState<KbFileDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);
  const [viewTab, setViewTab] = useState<"full" | "structure">("full");
  const [deleting, setDeleting] = useState<KbFileSummary | null>(null);
  const [deleteBusy, setDeleteBusy] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const [toast, setToast] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement | null>(null);
  const toastTimerRef = useRef<number | null>(null);

  const showToast = useCallback((message: string) => {
    setToast(message);
    if (toastTimerRef.current) window.clearTimeout(toastTimerRef.current);
    toastTimerRef.current = window.setTimeout(() => setToast(null), 2600);
  }, []);

  useEffect(() => () => {
    if (toastTimerRef.current) window.clearTimeout(toastTimerRef.current);
  }, []);

  const loadFiles = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await fetch(`${apiBase}/api/kb/files?kb_id=kb_cs_college`);
      const data = await response.json().catch(() => null);
      if (!response.ok) throw new Error(responseError(data, `HTTP ${response.status}`));
      setFiles(Array.isArray(data?.items) ? data.items : []);
    } catch (err) {
      setError(`文件列表加载失败：${err instanceof Error ? err.message : "未知错误"}`);
    } finally {
      setLoading(false);
    }
  }, [apiBase]);

  useEffect(() => {
    void loadFiles();
  }, [loadFiles]);

  const totals = useMemo(
    () => ({
      files: files.length,
      parents: files.reduce((sum, file) => sum + file.parent_count, 0),
      children: files.reduce((sum, file) => sum + file.child_count, 0),
      characters: files.reduce((sum, file) => sum + file.character_count, 0),
    }),
    [files]
  );

  const filteredFiles = useMemo(() => {
    const keyword = query.trim().toLowerCase();
    if (!keyword) return files;
    return files.filter((file) =>
      `${file.display_name} ${file.original_name} ${file.file_id}`.toLowerCase().includes(keyword)
    );
  }, [files, query]);

  const uploadFile = useCallback(async (file: File) => {
    if (ingest?.status === "processing") return;
    setIngest({ name: file.name, status: "processing", message: "解析、切片并写入知识库" });
    try {
      const body = new FormData();
      body.append("file", file);
      body.append("kb_id", "kb_cs_college");
      body.append("write_vectors", "true");
      body.append("fail_on_vector_error", "true");
      const response = await fetch(`${apiBase}/api/ingest/upload`, { method: "POST", body });
      const data = await response.json().catch(() => null);
      if (!response.ok) throw new Error(responseError(data, `HTTP ${response.status}`));
      setIngest({
        name: file.name,
        status: "ready",
        message: `已写入 ${data.parent_upserts} 个父块、${data.vector_upserts} 个子块向量`,
      });
      await loadFiles();
      showToast(`已入库：${file.name}`);
    } catch (err) {
      setIngest({
        name: file.name,
        status: "error",
        message: err instanceof Error ? err.message : "入库失败",
      });
    }
  }, [apiBase, ingest?.status, loadFiles, showToast]);

  const handleFileInput = (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (file) void uploadFile(file);
  };

  const handleDrop = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    setDragOver(false);
    const file = event.dataTransfer.files?.[0];
    if (file) void uploadFile(file);
  };

  const openFile = useCallback(async (file: KbFileSummary) => {
    setViewing(file);
    setDetail(null);
    setDetailError(null);
    setDetailLoading(true);
    setViewTab("full");
    try {
      const response = await fetch(`${apiBase}/api/kb/files/${encodeURIComponent(file.file_id)}?include_children=true`);
      const data = await response.json().catch(() => null);
      if (!response.ok) throw new Error(responseError(data, `HTTP ${response.status}`));
      setDetail(data as KbFileDetail);
    } catch (err) {
      setDetailError(`文件读取失败：${err instanceof Error ? err.message : "未知错误"}`);
    } finally {
      setDetailLoading(false);
    }
  }, [apiBase]);

  const confirmDelete = useCallback(async () => {
    if (!deleting || deleteBusy) return;
    setDeleteBusy(true);
    setDeleteError(null);
    try {
      const response = await fetch(`${apiBase}/api/kb/files/${encodeURIComponent(deleting.file_id)}`, {
        method: "DELETE",
      });
      const data = await response.json().catch(() => null);
      if (!response.ok) throw new Error(responseError(data, `HTTP ${response.status}`));
      const deletedName = deleting.display_name;
      setDeleting(null);
      await loadFiles();
      showToast(`已出库：${deletedName}`);
    } catch (err) {
      setDeleteError(err instanceof Error ? err.message : "出库失败");
    } finally {
      setDeleteBusy(false);
    }
  }, [apiBase, deleteBusy, deleting, loadFiles, showToast]);

  return (
    <div className="flex-1 overflow-y-auto bg-white">
      <div className="mx-auto w-full max-w-6xl px-5 py-7 sm:px-8">
        <div>
          <p className="text-xs font-medium text-slate-400">知识库 / 文件管理</p>
          <h2 className="mt-1 text-2xl font-bold text-slate-950">文件管理</h2>
          <p className="mt-2 text-sm text-slate-500">管理已入库文档、父块全文与 Milvus 子块向量。</p>
        </div>

        <div className="mt-5 grid grid-cols-2 gap-3 lg:grid-cols-4">
          <Stat icon={<FileText className="h-4 w-4" />} label="文件" value={formatNumber(totals.files)} />
          <Stat icon={<Layers className="h-4 w-4" />} label="父块" value={formatNumber(totals.parents)} />
          <Stat icon={<Boxes className="h-4 w-4" />} label="子块 / 向量" value={formatNumber(totals.children)} />
          <Stat icon={<Hash className="h-4 w-4" />} label="字符" value={formatNumber(totals.characters)} />
        </div>

        <div
          onDragOver={(event) => {
            event.preventDefault();
            setDragOver(true);
          }}
          onDragLeave={() => setDragOver(false)}
          onDrop={handleDrop}
          className={`mt-5 rounded-lg border-2 border-dashed px-5 py-6 transition ${
            dragOver ? "border-slate-900 bg-slate-50" : "border-slate-200 bg-white"
          }`}
        >
          {ingest ? (
            <div className="flex flex-col gap-4 sm:flex-row sm:items-center" role="status" aria-live="polite">
              <div className={`flex h-11 w-11 shrink-0 items-center justify-center rounded-full ${ingest.status === "error" ? "bg-rose-50 text-rose-600" : ingest.status === "ready" ? "bg-emerald-50 text-emerald-600" : "bg-slate-100 text-slate-700"}`}>
                {ingest.status === "processing" ? <Loader2 className="h-5 w-5 animate-spin" /> : ingest.status === "ready" ? <Check className="h-5 w-5" /> : <AlertTriangle className="h-5 w-5" />}
              </div>
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-semibold text-slate-900">{ingest.name}</p>
                <p className={`mt-1 text-xs ${ingest.status === "error" ? "text-rose-600" : "text-slate-500"}`}>
                  {ingest.status === "processing" ? "processing · " : ingest.status === "ready" ? "ready · " : "failed · "}
                  {ingest.message}
                </p>
              </div>
              {ingest.status !== "processing" && (
                <button type="button" onClick={() => inputRef.current?.click()} className="rounded-lg border border-slate-200 px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50">
                  继续入库
                </button>
              )}
            </div>
          ) : (
            <div className="flex flex-col items-center text-center">
              <div className="flex h-11 w-11 items-center justify-center rounded-full bg-slate-100 text-slate-700">
                <UploadCloud className="h-5 w-5" />
              </div>
              <p className="mt-3 text-sm font-medium text-slate-800">拖拽文件到这里，或选择文件入库</p>
              <button type="button" onClick={() => inputRef.current?.click()} className="mt-3 inline-flex items-center gap-2 rounded-lg bg-slate-950 px-4 py-2 text-sm font-medium text-white hover:bg-black">
                <UploadCloud className="h-4 w-4" />
                选择文件
              </button>
              <p className="mt-2 text-xs text-slate-400">PDF / DOCX / TXT / MD</p>
            </div>
          )}
          <input ref={inputRef} type="file" accept={ACCEPTED_TYPES} className="hidden" onChange={handleFileInput} />
        </div>

        <div className="mt-6 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <label className="relative block w-full sm:max-w-sm">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
            <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索文件名或 file_id" className="h-10 w-full rounded-lg border border-slate-200 bg-white pl-9 pr-3 text-sm outline-none focus:border-slate-400 focus:ring-2 focus:ring-slate-100" />
          </label>
          <div className="flex items-center justify-between gap-3 text-sm text-slate-500 sm:justify-end">
            <span>共 {filteredFiles.length} 个文件</span>
            <button type="button" onClick={() => void loadFiles()} disabled={loading} className="flex h-9 w-9 items-center justify-center rounded-lg text-slate-500 hover:bg-slate-100 hover:text-slate-900 disabled:opacity-50" aria-label="刷新文件列表" title="刷新">
              <RefreshCw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} />
            </button>
          </div>
        </div>

        <div className="mt-3">
          {loading && files.length === 0 ? (
            <div className="flex min-h-40 items-center justify-center gap-2 border-y border-slate-200 text-sm text-slate-500">
              <Loader2 className="h-4 w-4 animate-spin" />
              正在加载文件
            </div>
          ) : error ? (
            <div className="rounded-lg border border-rose-200 bg-rose-50 px-4 py-4 text-sm text-rose-700">{error}</div>
          ) : filteredFiles.length === 0 ? (
            <div className="border-y border-slate-200 py-14 text-center">
              <FileText className="mx-auto h-7 w-7 text-slate-300" />
              <p className="mt-3 text-sm text-slate-500">暂无匹配文件</p>
            </div>
          ) : (
            <ul className="space-y-2">
              {filteredFiles.map((file) => (
                <li key={file.file_id} className="rounded-lg border border-slate-200 bg-white px-4 py-4 transition hover:border-slate-300 hover:shadow-sm">
                  <div className="flex flex-col gap-4 md:flex-row md:items-center">
                    <div className="flex min-w-0 flex-1 items-start gap-3">
                      <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-slate-100">
                        <FileText className="h-4 w-4 text-slate-600" />
                      </div>
                      <div className="min-w-0">
                        <div className="flex min-w-0 flex-wrap items-center gap-2">
                          <h3 className="max-w-full truncate text-sm font-semibold text-slate-950" title={file.display_name}>{file.display_name}</h3>
                          <span className="rounded-md border border-slate-200 px-1.5 py-0.5 text-[11px] font-medium text-slate-600">{file.file_type}</span>
                          <StatusBadge status={file.status} />
                        </div>
                        <p className="mt-1 truncate text-xs text-slate-400" title={file.original_name}>{file.original_name}</p>
                        <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-slate-500">
                          <span>{file.parent_count} 父块</span>
                          <span>{file.child_count} 子块 / 向量</span>
                          <span>{formatNumber(file.character_count)} 字符</span>
                          <span>{formatDate(file.ingested_at)}</span>
                        </div>
                      </div>
                    </div>
                    <div className="flex shrink-0 items-center gap-2">
                      <button type="button" onClick={() => void openFile(file)} className="inline-flex items-center gap-2 rounded-lg border border-slate-200 px-3 py-2 text-xs font-medium text-slate-700 hover:bg-slate-50">
                        <Eye className="h-4 w-4" />
                        查看
                      </button>
                      <button type="button" onClick={() => { setDeleting(file); setDeleteError(null); }} className="inline-flex items-center gap-2 rounded-lg border border-rose-200 px-3 py-2 text-xs font-medium text-rose-600 hover:bg-rose-50">
                        <Trash2 className="h-4 w-4" />
                        一键出库
                      </button>
                    </div>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>

      {viewing && (
        <ViewFileModal
          file={viewing}
          detail={detail}
          loading={detailLoading}
          error={detailError}
          tab={viewTab}
          onTabChange={setViewTab}
          onClose={() => setViewing(null)}
        />
      )}
      {deleting && (
        <DeleteFileModal
          file={deleting}
          deleting={deleteBusy}
          error={deleteError}
          onCancel={() => setDeleting(null)}
          onConfirm={() => void confirmDelete()}
        />
      )}
      {toast && (
        <div className="fixed bottom-6 left-1/2 z-[60] -translate-x-1/2 rounded-lg bg-slate-950 px-4 py-2.5 text-sm text-white shadow-lg" role="status" aria-live="polite">
          <span className="inline-flex items-center gap-2"><Check className="h-4 w-4 text-emerald-400" />{toast}</span>
        </div>
      )}
    </div>
  );
}
