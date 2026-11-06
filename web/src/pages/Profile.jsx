import { useEffect, useState } from "react";
import { api } from "../api.js";

const SKIN_TONES = [
  { key: "warm", label: "暖调" },
  { key: "cool", label: "冷调" },
  { key: "neutral", label: "中性" },
];

const empty = {
  height_cm: "",
  weight_kg: "",
  chest_cm: "",
  waist_cm: "",
  hip_cm: "",
  shoulder_cm: "",
  inseam_cm: "",
  skin_tone: "neutral",
};

const number = (value) => (value === "" || value === null ? null : Number(value));

export default function Profile({ status }) {
  const [form, setForm] = useState(empty);
  const [report, setReport] = useState(null);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  const load = async () => {
    try {
      const body = await api.profile();
      if (body.profile) {
        setForm({
          ...empty,
          ...Object.fromEntries(
            Object.entries(body.profile).map(([key, value]) => [key, value ?? ""])
          ),
        });
        setReport(body.report);
      }
    } catch (loadError) {
      setError(loadError.message);
    }
  };

  useEffect(() => {
    load();
  }, []);

  const update = (patch) => setForm((value) => ({ ...value, ...patch }));

  const submit = async (event) => {
    event.preventDefault();
    if (!form.height_cm || !form.weight_kg) {
      setError("身高和体重至少要填。");
      return;
    }
    setSaving(true);
    setError("");
    setMessage("");
    try {
      await api.saveProfile({
        height_cm: Number(form.height_cm),
        weight_kg: Number(form.weight_kg),
        chest_cm: number(form.chest_cm),
        waist_cm: number(form.waist_cm),
        hip_cm: number(form.hip_cm),
        shoulder_cm: number(form.shoulder_cm),
        inseam_cm: number(form.inseam_cm),
        skin_tone: form.skin_tone,
      });
      setMessage("存好了。");
      await load();
    } catch (saveError) {
      setError(saveError.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-3xl font-semibold tracking-tight">我的</h1>
        <p className="mt-1 text-sm text-muted">
          {status ? `衣橱 ${status.active} 件在穿` : ""}
        </p>
      </header>

      <form className="space-y-4" onSubmit={submit}>
        <div className="grid grid-cols-2 gap-3">
          <label className="block">
            <span className="label">身高 cm</span>
            <input
              className="field tabular-nums"
              inputMode="decimal"
              value={form.height_cm}
              onChange={(event) => update({ height_cm: event.target.value })}
            />
          </label>
          <label className="block">
            <span className="label">体重 kg</span>
            <input
              className="field tabular-nums"
              inputMode="decimal"
              value={form.weight_kg}
              onChange={(event) => update({ weight_kg: event.target.value })}
            />
          </label>
        </div>

        <p className="text-xs leading-relaxed text-muted">
          下面三项可以不填，但填了版型建议会具体很多。量法：胸围过最高点、腰围过肚脐上一指、臀围过最宽处。
        </p>

        <div className="grid grid-cols-3 gap-3">
          {[
            ["chest_cm", "胸围"],
            ["waist_cm", "腰围"],
            ["hip_cm", "臀围"],
          ].map(([key, label]) => (
            <label className="block" key={key}>
              <span className="label">{label}</span>
              <input
                className="field tabular-nums"
                inputMode="decimal"
                value={form[key]}
                onChange={(event) => update({ [key]: event.target.value })}
              />
            </label>
          ))}
        </div>

        <div className="grid grid-cols-2 gap-3">
          {[
            ["shoulder_cm", "肩宽"],
            ["inseam_cm", "裤长"],
          ].map(([key, label]) => (
            <label className="block" key={key}>
              <span className="label">{label}</span>
              <input
                className="field tabular-nums"
                inputMode="decimal"
                value={form[key]}
                onChange={(event) => update({ [key]: event.target.value })}
              />
            </label>
          ))}
        </div>

        <div>
          <span className="label">肤色冷暖</span>
          <div className="flex gap-2">
            {SKIN_TONES.map((item) => (
              <button
                type="button"
                key={item.key}
                onClick={() => update({ skin_tone: item.key })}
                className={`chip ${form.skin_tone === item.key ? "chip-active" : ""}`}
              >
                {item.label}
              </button>
            ))}
          </div>
          <p className="mt-2 text-[11px] text-muted/70">
            拿不准就看手腕血管：偏蓝紫是冷调，偏绿是暖调。
          </p>
        </div>

        {error ? <p className="text-sm text-red-400">{error}</p> : null}
        {message ? <p className="text-sm text-brass">{message}</p> : null}

        <button className="btn w-full" type="submit" disabled={saving}>
          {saving ? "在存……" : "保存"}
        </button>
      </form>

      {report ? (
        <section className="card p-5">
          <p className="text-xs uppercase tracking-[0.2em] text-muted">体型</p>
          <p className="mt-2 text-lg">{report.summary}</p>
          <ul className="mt-3 space-y-2">
            {report.hints.map((hint) => (
              <li key={hint} className="flex gap-2 text-sm leading-relaxed text-muted">
                <span className="text-brass">·</span>
                {hint}
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      <section className="card p-5">
        <p className="text-xs uppercase tracking-[0.2em] text-muted">身体照片怎么拍</p>
        <ul className="mt-3 space-y-2 text-sm leading-relaxed text-muted">
          <li>· 白墙前，正对窗，不要逆光也不要开美颜</li>
          <li>· 手机架在胸口高度，拍全身，脚背要拍到</li>
          <li>· 穿深色贴身背心＋短裤，别穿宽松衣服</li>
          <li>· 一张就够，比多拍十张有用的是把三围量准</li>
        </ul>
        <p className="mt-3 text-[11px] leading-relaxed text-muted/70">
          不建议拍裸照：多数图像模型对裸露图像有安全过滤会直接拒图，贴身衣物反而更容易看出肩线和腿长，而且泄露代价完全不同。照片上传功能在 M2 接入。
        </p>
      </section>
    </div>
  );
}
