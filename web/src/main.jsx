import React, { useState, useEffect, useRef } from "react";
import { createRoot } from "react-dom/client";
import {
  Terminal,
  Play,
  ArrowUpRight,
  CheckCircle2,
  Clock,
  GitBranch,
  Layers,
  Activity,
  FileCode2,
  History,
  ChevronRight,
  AlertCircle,
  RefreshCw,
  FlaskConical,
  SquareCode,
} from "lucide-react";
import "./style.css";
const api = async (path, options) => {
  const r = await fetch("/api" + path, options);
  const text = await r.text();
  let data;
  try {
    data = JSON.parse(text);
  } catch {
    throw Error("服务暂时不可用，请检查后台日志");
  }
  if (!r.ok)
    throw Error(
      typeof data.detail === "string" ? data.detail : "请求字段不完整",
    );
  return data;
};
const post = (path, body) =>
  api(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
const statusLabel = {
  queued: "准备启动",
  running: "正在执行",
  completed: "执行完成",
  failed: "执行失败",
  interrupted: "执行中断",
};
const phaseLabel = {
  understanding: "理解需求",
  exploring: "探索仓库",
  planning: "制定计划",
  implementing: "修改代码",
  verifying: "测试验证",
  repairing: "修复问题",
  completed: "执行完成",
};
function App() {
  const [tasks, setTasks] = useState([]),
    [env, setEnv] = useState({}),
    [jobs, setJobs] = useState([]),
    [selected, setSelected] = useState("DEV-001"),
    [jobId, setJobId] = useState(() =>
      new URLSearchParams(location.search).get("job"),
    ),
    [job, setJob] = useState(null),
    [events, setEvents] = useState([]),
    [diff, setDiff] = useState(""),
    [tab, setTab] = useState("verification"),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false),
    [form, setForm] = useState({ title: "", description: "", criteria: "" }),
    [replay, setReplay] = useState(false),
    [playing, setPlaying] = useState(false),
    [position, setPosition] = useState(0),
    [speed, setSpeed] = useState(1),
    [caseIndex, setCaseIndex] = useState(0);
  const cursor = useRef(0),
    selection = useRef(null);
  const refresh = () =>
    api("/jobs")
      .then(setJobs)
      .catch((e) => setError(e.message));
  useEffect(() => {
    Promise.all([api("/tasks"), api("/environment"), api("/jobs")])
      .then(([t, e, j]) => {
        setTasks(t);
        setEnv(e);
        setJobs(j);
      })
      .catch((e) => setError(e.message));
  }, []);
  useEffect(() => {
    const timer = setInterval(() => {
      api("/jobs")
        .then(setJobs)
        .catch((e) => setError(e.message));
    }, 3000);
    return () => clearInterval(timer);
  }, []);
  useEffect(() => {
    if (!jobId) return;
    selection.current = jobId;
    cursor.current = 0;
    setEvents([]);
    setJob(null);
    setDiff("");
    let alive = true;
    let timer;
    const poll = async () => {
      try {
        const [j, e, d] = await Promise.all([
          api("/jobs/" + jobId),
          api("/jobs/" + jobId + "/events?cursor=" + cursor.current),
          api("/jobs/" + jobId + "/diff"),
        ]);
        if (!alive) return;
        setJob(j);
        setSelected(
          j.mode === "smoke"
            ? "smoke"
            : j.task.id.startsWith("DEV-")
              ? j.task.id
              : "custom",
        );
        setError("");
        setEvents((old) => [...old, ...e.events]);
        cursor.current = e.cursor;
        setDiff(d.diff);
        refresh();
        if (["queued", "running"].includes(j.status) || e.events.length === 500)
          timer = setTimeout(poll, 1000);
      } catch (e) {
        if (alive) {
          setError(e.message);
          timer = setTimeout(poll, 3000);
        }
      }
    };
    poll();
    return () => {
      alive = false;
      clearTimeout(timer);
    };
  }, [jobId]);
  useEffect(() => {
    if (!playing) return;
    const timer = setInterval(
      () =>
        setPosition((p) => {
          if (p >= events.length) {
            setPlaying(false);
            return p;
          }
          return p + 1;
        }),
      1000 / speed,
    );
    return () => clearInterval(timer);
  }, [playing, speed, events.length]);
  const choose = (id) => {
    history.replaceState(null, "", id ? "?job=" + id : location.pathname);
    setJobId(id);
    setReplay(false);
    setPlaying(false);
    setPosition(0);
    setError("");
    const selectedJob = jobs.find((j) => j.job_id === id);
    if (selectedJob)
      setSelected(
        selectedJob.mode === "smoke"
          ? "smoke"
          : selectedJob.task.id.startsWith("DEV-")
            ? selectedJob.task.id
            : "custom",
      );
  };
  const start = async (smoke = false) => {
    setBusy(true);
    setError("");
    try {
      const body = smoke
        ? { smoke: true }
        : selected === "custom"
          ? {
              title: job?.task.title || form.title,
              description: job?.task.description || form.description,
              acceptance_criteria:
                job?.task.acceptance_criteria ||
                form.criteria.split("\n").filter((x) => x.trim()),
            }
          : { issue_id: selected };
      const j = await post("/jobs", body);
      choose(j.job_id);
      refresh();
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };
  const compare = async () => {
    setBusy(true);
    setError("");
    try {
      const c = await post("/jobs/" + jobId + "/compare", {});
      setJob((j) => ({ ...j, comparison: c }));
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };
  const task = job?.task || tasks.find((t) => t.id === selected),
    active = jobs.some((j) => ["queued", "running"].includes(j.status)),
    visible = replay ? events.slice(0, position) : events,
    result = job?.result,
    coverage =
      job?.comparison?.acceptance_coverage || result?.acceptance_coverage || [],
    evaluation = job?.evaluation;
  const latestPhase = [...visible]
    .reverse()
    .find((e) => e.data?.to || e.data?.phase);
  const phase = latestPhase?.data?.to || latestPhase?.data?.phase;
  const stage = {
    understanding: 0,
    exploring: 1,
    planning: 2,
    implementing: 3,
    repairing: 3,
    verifying: 4,
    completed: 5,
  }[phase];
  return (
    <div className="shell">
      <aside className="sidebar">
        <a className="brand" href="/">
          <span className="brand-icon">
            <Terminal size={22} />
          </span>
          DevPilot<span className="version">V1</span>
        </a>
        <div className="workspace-label">LOCAL WORKSPACE</div>
        <div className="nav active">
          <Layers size={18} />
          研发工作台
          <span className="nav-dot" />
        </div>
        <div className="section-label">
          <History size={14} />
          运行记录
          <button
            title="刷新记录"
            onClick={() => refresh().catch((e) => setError(e.message))}
          >
            <RefreshCw size={13} />
          </button>
        </div>
        <div className="history">
          {jobs.length === 0 ? (
            <div className="history-empty">
              尚无工作台运行记录
              <br />
              启动任务，开始积累证据。
            </div>
          ) : (
            jobs.map((j) => (
              <button
                className={
                  "history-item " + (j.job_id === jobId ? "chosen" : "")
                }
                key={j.job_id}
                onClick={() => choose(j.job_id)}
              >
                <span className={"dot " + j.status} />
                <span>
                  <strong>{j.task.title}</strong>
                  <small>
                    {j.mode === "smoke"
                      ? "流程自检"
                      : j.mode === "unknown"
                        ? "旧记录 · 来源未知"
                        : "真实模型"}{" "}
                    · {statusLabel[j.status]}
                  </small>
                  <small>
                    {j.model} ·{" "}
                    {new Date(j.created_at).toLocaleString("zh-CN", {
                      month: "2-digit",
                      day: "2-digit",
                      hour: "2-digit",
                      minute: "2-digit",
                      hour12: false,
                    })}
                  </small>
                </span>
              </button>
            ))
          )}
        </div>
        <div className="sidebar-bottom">
          <span className="online" />
          本地可信环境<div>Custom Runtime · 单任务执行</div>
        </div>
      </aside>
      <main>
        <header>
          <span>
            工作空间 <ChevronRight size={14} /> ShopFlow{" "}
            <ChevronRight size={14} />
            <b>研发任务</b>
          </span>
          <span className="local-tag">
            <span className="online" /> LOCAL ONLY
          </span>
        </header>
        <section className="heading">
          <div>
            <div className="eyebrow">BUILD. VERIFY. UNDERSTAND.</div>
            <h1>
              让每一次修改，都有据可查<span>。</span>
            </h1>
            <p>
              从需求到代码，从测试到业务效果。观察 Agent
              的每一步，验证最终交付。
            </p>
          </div>
          <div className="runtime-tag">
            <SquareCode size={20} />
            <div>
              <strong>自研 Agent Runtime</strong>
              <small>可追溯 · 可验证 · 本地运行</small>
            </div>
          </div>
        </section>
        {error && (
          <div role="alert" className="error">
            <AlertCircle size={18} />
            {error}
            <button onClick={() => setError("")}>关闭</button>
          </div>
        )}
        <div className="metrics">
          <Metric
            icon={<GitBranch size={19} />}
            label="目标项目"
            value="ShopFlow"
            detail="订单服务 · Python / FastAPI"
          />
          <Metric
            icon={<Activity size={19} />}
            label="执行模型"
            value={job?.model || env.model || "读取中"}
            detail={
              job?.mode === "smoke"
                ? "确定性流程自检"
                : env.configured
                  ? "已读取服务端配置"
                  : "尚未配置 API Key"
            }
          />
          <Metric
            icon={<Clock size={19} />}
            label="运行状态"
            value={job ? statusLabel[job.status] : "等待任务"}
            detail={
              result
                ? `${result.total_steps} 步 · ${(result.duration_ms / 1000).toFixed(1)} 秒`
                : "每次执行使用独立工作区"
            }
          />
          <Metric
            icon={<CheckCircle2 size={19} />}
            label="验收覆盖"
            value={
              result
                ? `${coverage.filter((c) => c.status === "verified").length} / ${coverage.length}`
                : "—"
            }
            detail="仅计入有确定性证据的条件"
          />
        </div>
        <div className="workgrid">
          <section className="panel task-panel">
            <div className="panel-title">
              <span>
                <FileCode2 size={18} />
                任务说明
              </span>
              <span className="mini-tag">01 / INPUT</span>
            </div>
            <label className="field-label" htmlFor="task">
              选择研发任务
            </label>
            <select
              id="task"
              value={selected}
              onChange={(e) => {
                setSelected(e.target.value);
                history.replaceState(null, "", location.pathname);
                setJobId(null);
                setJob(null);
                setEvents([]);
                setDiff("");
              }}
            >
              {tasks.map((t) => (
                <option key={t.id} value={t.id}>
                  {t.id} · {t.title}
                </option>
              ))}
              {selected === "smoke" && (
                <option value="smoke" disabled>
                  流程自检：计算器修复
                </option>
              )}
              <option value="custom">自定义 ShopFlow 需求</option>
            </select>
            {selected === "custom" && !job ? (
              <div className="custom">
                <input
                  aria-label="需求标题"
                  placeholder="需求标题"
                  value={form.title}
                  onChange={(e) => setForm({ ...form, title: e.target.value })}
                />
                <textarea
                  aria-label="需求描述"
                  placeholder="详细描述需要实现的行为"
                  value={form.description}
                  onChange={(e) =>
                    setForm({ ...form, description: e.target.value })
                  }
                />
                <textarea
                  aria-label="验收条件"
                  placeholder="验收条件，每行一条"
                  value={form.criteria}
                  onChange={(e) =>
                    setForm({ ...form, criteria: e.target.value })
                  }
                />
              </div>
            ) : (
              <>
                <div className="task-id">
                  {task?.id || "DEV-001"}
                  <span>研发任务</span>
                </div>
                <h2>{task?.title || "正在读取任务"}</h2>
                <p className="description">{task?.description}</p>
                <div className="field-label">验收条件</div>
                <ul className="criteria">
                  {task?.acceptance_criteria?.map((c, i) => (
                    <li key={i}>
                      <span>{String(i + 1).padStart(2, "0")}</span>
                      {c}
                    </li>
                  ))}
                </ul>
              </>
            )}
            <div className="task-footer">
              <div className="budget">
                预算上限：{env.max_steps || "—"} 步 /{" "}
                {env.max_run_seconds || "—"} 秒
              </div>
              <button
                className="primary"
                disabled={busy || active || selected === "smoke"}
                onClick={() => start()}
              >
                <Play size={16} />
                {active ? "任务执行中" : "启动真实任务"}
                <ArrowUpRight size={16} />
              </button>
              <button
                className="secondary"
                disabled={busy || active}
                onClick={() => start(true)}
              >
                <FlaskConical size={15} />
                流程自检：计算器修复
              </button>
              <small>自检不调用模型，不计入业务能力评测。</small>
            </div>
          </section>
          <section className="panel execution">
            <div className="panel-title">
              <span>
                <Activity size={18} />
                执行过程{" "}
                {job && (
                  <em className={"badge " + job.status}>
                    {statusLabel[job.status]}
                  </em>
                )}
              </span>
              <span className="mini-tag">02 / EXECUTION</span>
            </div>
            <div className="phase-track">
              {["理解", "探索", "计划", "修改", "验证", "交付"].map((p, i) => (
                <React.Fragment key={p}>
                  <span className={i === stage ? "current-phase" : ""}>
                    {String(i + 1).padStart(2, "0")}
                    <b>{p}</b>
                  </span>
                  {i < 5 && <ChevronRight size={13} />}
                </React.Fragment>
              ))}
            </div>
            {job && !["running", "queued"].includes(job.status) && (
              <div className="replay">
                <button
                  onClick={() => {
                    setReplay(true);
                    setPosition(0);
                    setPlaying(true);
                  }}
                >
                  <Play size={13} />
                  历史回放
                </button>
                {replay && (
                  <>
                    <b>
                      历史回放 {position}/{events.length}
                    </b>
                    <button onClick={() => setPlaying(!playing)}>
                      {playing ? "暂停" : "继续"}
                    </button>
                    <select
                      aria-label="回放速度"
                      value={speed}
                      onChange={(e) => setSpeed(Number(e.target.value))}
                    >
                      <option value={1}>1×</option>
                      <option value={2}>2×</option>
                      <option value={4}>4×</option>
                    </select>
                    <button
                      onClick={() => {
                        setReplay(false);
                        setPlaying(false);
                      }}
                    >
                      查看全部
                    </button>
                  </>
                )}
              </div>
            )}
            <div className="timeline">
              {!visible.length ? (
                <div className="empty">
                  <div className="empty-icon">
                    <Terminal size={30} />
                  </div>
                  <h3>
                    {job ? "等待执行事件" : "准备好，开始一次可验证的交付"}
                  </h3>
                  <p>
                    选择左侧任务并启动。工具调用、测试反馈和修复过程将在这里逐步呈现。
                  </p>
                  <div className="empty-flow">
                    需求 <ChevronRight size={14} /> 代码{" "}
                    <ChevronRight size={14} /> 测试 <ChevronRight size={14} />{" "}
                    证据
                  </div>
                </div>
              ) : (
                visible.map((e, i) => <Event key={i} event={e} index={i} />)
              )}
            </div>
            <div className="evidence-note">
              <GitBranch size={14} />
              {job?.run_id || "等待生成 Run ID"}
              <span>
                {job?.mode === "smoke"
                  ? "流程自检 · 非业务能力证明"
                  : job
                    ? job.mode === "unknown"
                      ? "旧记录 · 来源未知"
                      : "真实模型 · 证据持续落盘"
                    : "执行记录保存在本机"}
              </span>
            </div>
          </section>
        </div>
        <section className="panel results">
          <div className="result-top">
            <div className="tabs">
              {[
                ["verification", "验证结果"],
                ["diff", "代码 Diff"],
                ["business", "业务效果"],
              ].map(([id, label]) => (
                <button
                  className={tab === id ? "selected" : ""}
                  key={id}
                  onClick={() => setTab(id)}
                >
                  {label}
                </button>
              ))}
            </div>
            <span className="mini-tag">03 / EVIDENCE</span>
          </div>
          {tab === "verification" ? (
            <div className="verification">
              <div>
                <h3>完成状态与需求验收，分别核验</h3>
                <p>
                  测试通过不自动代表所有自然语言条件已满足。未绑定检查的条件保持“未验证”。
                </p>
                {job?.error && job.status !== "completed" && (
                  <div className="error">{job.error}</div>
                )}
                <div className="evidence-cards">
                  <div>
                    <small>Runtime</small>
                    <strong>{result?.status || "等待执行"}</strong>
                  </div>
                  <div>
                    <small>独立隐藏验收</small>
                    <strong>
                      {evaluation?.evaluation_status ||
                        (job?.mode === "smoke" ? "不适用" : "尚未评测")}
                    </strong>
                  </div>
                  <div>
                    <small>可见测试</small>
                    <strong>
                      {result?.verification?.checks?.find(
                        (c) => c.name === "visible_tests",
                      )?.result?.status ||
                        evaluation?.verification?.visible?.status ||
                        "未获取"}
                    </strong>
                  </div>
                  <div>
                    <small>模型请求次数</small>
                    <strong>
                      {evaluation?.llm_requests ??
                        result?.budget?.llm_requests ??
                        "未获取"}
                    </strong>
                  </div>
                  <div>
                    <small>Token 用量</small>
                    <strong>{evaluation?.token_usage ?? "未获取"}</strong>
                  </div>
                </div>
              </div>
              <div className="coverage">
                {coverage.length ? (
                  coverage.map((c, i) => (
                    <div key={i}>
                      <span
                        className={
                          "badge " +
                          (c.status === "verified"
                            ? "completed"
                            : c.status === "failed"
                              ? "failed"
                              : "unknown")
                        }
                      >
                        {c.status === "verified"
                          ? "已验证"
                          : c.status === "failed"
                            ? "失败"
                            : "未验证"}
                      </span>
                      <span>{c.criterion}</span>
                    </div>
                  ))
                ) : (
                  <p>运行完成后，这里展示逐条验收覆盖和结果。</p>
                )}
                <details>
                  <summary>查看原始验证证据</summary>
                  <pre>
                    {JSON.stringify(result?.verification || {}, null, 2)}
                  </pre>
                </details>
              </div>
            </div>
          ) : tab === "diff" ? (
            <div className="diff">
              <div className="code-heading">
                <FileCode2 size={15} />
                final.diff <span>来自当前运行产物</span>
              </div>
              <pre>
                {diff
                  ? diff.split("\n").map((line, i) => (
                      <div
                        key={i}
                        className={
                          line.startsWith("+")
                            ? "addition"
                            : line.startsWith("-")
                              ? "deletion"
                              : ""
                        }
                      >
                        <span className="line-number">{i + 1}</span>
                        {line || " "}
                      </div>
                    ))
                  : "暂无代码差异。运行任务后查看实际修改。"}
              </pre>
            </div>
          ) : (
            <div className="business">
              <div className="business-heading">
                <div>
                  <h3>订单筛选 · 修改前后对比</h3>
                  <p>
                    相同订单数据，实际应用路由响应。每次比较使用独立数据库。
                  </p>
                </div>
                <button
                  className="primary"
                  disabled={
                    busy ||
                    job?.task.id !== "DEV-001" ||
                    job?.mode !== "real" ||
                    !["completed", "failed"].includes(job?.status)
                  }
                  onClick={compare}
                >
                  <Play size={15} />
                  {busy ? "正在核验" : "运行业务对比"}
                </button>
              </div>
              <div className="case-tabs">
                {[
                  "仅查看 paid 订单",
                  "非法状态返回 400",
                  "不传状态保持兼容",
                ].map((s, i) => (
                  <button
                    className={caseIndex === i ? "selected" : ""}
                    key={s}
                    onClick={() => setCaseIndex(i)}
                  >
                    {s}
                  </button>
                ))}
              </div>
              {job?.comparison ? (
                <>
                  <div className="comparison">
                    {["before", "after"].map((side) => {
                      const data = job.comparison[side],
                        c = data?.cases?.[caseIndex];
                      return (
                        <div key={side}>
                          <h4>
                            {side === "before"
                              ? "修改前 · 缺陷起点"
                              : "修改后 · Agent 候选代码"}
                            {c && (
                              <span
                                className={
                                  "badge " + (c.passed ? "completed" : "failed")
                                }
                              >
                                {c.passed ? "检查通过" : "检查失败"}
                              </span>
                            )}
                          </h4>
                          <code>
                            {c?.request || "执行异常"} · HTTP {c?.status || "—"}
                          </code>
                          {Array.isArray(c?.body) && (
                            <table className="orders-table">
                              <thead>
                                <tr>
                                  <th>订单</th>
                                  <th>状态</th>
                                  <th>金额</th>
                                </tr>
                              </thead>
                              <tbody>
                                {c.body.map((order, i) => (
                                  <tr key={order.id ?? i}>
                                    <td>#{order.id}</td>
                                    <td>
                                      <span
                                        className={
                                          "badge " +
                                          (order.status === "paid"
                                            ? "completed"
                                            : "unknown")
                                        }
                                      >
                                        {order.status}
                                      </span>
                                    </td>
                                    <td>{order.total_amount}</td>
                                  </tr>
                                ))}
                              </tbody>
                            </table>
                          )}
                          <details open={!Array.isArray(c?.body)}>
                            <summary>原始接口响应</summary>
                            <pre>
                              {JSON.stringify(c?.body || data?.error, null, 2)}
                            </pre>
                          </details>
                        </div>
                      );
                    })}
                  </div>
                  <p className="hash">
                    候选代码 SHA-256：{job.comparison.candidate_sha256}
                    <br />
                    证据时间：{job.comparison.created_at}
                  </p>
                </>
              ) : (
                <div className="business-empty">
                  完成真实 DEV-001 运行后，可核验订单筛选效果。
                  <br />
                  其他任务暂未提供专用业务对比；请查看验证结果和代码 Diff。
                </div>
              )}
            </div>
          )}
        </section>
        <footer>
          DevPilot / Agent Engineering Lab
          <span>所有结论都应能回到具体证据。</span>
        </footer>
      </main>
    </div>
  );
}
function Metric({ icon, label, value, detail }) {
  return (
    <div className="metric">
      <div className="metric-label">
        {label}
        {icon}
      </div>
      <strong>{value}</strong>
      <small>{detail}</small>
    </div>
  );
}
function Event({ event: e, index }) {
  const d = e.data || {},
    bad = e.event === "run_failed" || d.success === false;
  return (
    <article className={"event " + (bad ? "bad" : "")}>
      <div className="event-marker">
        {bad ? <AlertCircle size={15} /> : <CheckCircle2 size={15} />}
      </div>
      <div className="event-body">
        <div className="event-heading">
          <strong>{d.tool || phaseLabel[d.to || d.phase] || e.event}</strong>
          <small>
            {new Date(e.timestamp).toLocaleTimeString("zh-CN", {
              hour12: false,
            })}
          </small>
        </div>
        <p>
          {{
            run_started: "已读取需求与验收条件",
            tool_called: "调用受控工具",
            tool_result:
              d.success === false
                ? "工具返回失败，交由 Runtime 处理"
                : "工具执行结果已记录",
            verifier_started: "正在执行独立最终验证",
            verifier_result: d.success ? "最终验证通过" : "最终验证未通过",
            run_completed: "执行完成，交付产物已保存",
            run_failed: "执行失败，诊断证据已保留",
            phase_changed: "阶段推进",
          }[e.event] || e.event}
        </p>
        {d.summary && (
          <p className="tool-summary">{String(d.summary).slice(0, 500)}</p>
        )}
        <details>
          <summary>
            事件 {String(index + 1).padStart(2, "0")} · 查看数据
          </summary>
          <pre>{JSON.stringify(d, null, 2)}</pre>
        </details>
      </div>
    </article>
  );
}
createRoot(document.getElementById("root")).render(<App />);
