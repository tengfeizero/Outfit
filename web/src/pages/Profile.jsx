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
  const [city, setCity] = useState("");
  const [cityMessage, setCityMessage] = useState("");
  const [savingCity, setSavingCity] = useState(false);
  const [bodyPreview, setBodyPreview] = useState(null);
  const [uploadingBody, setUploadingBody] = useState(false);

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
        if (body.profile.photo_full) setBodyPreview(`/media/${body.profile.photo_full}`);
      }
    } catch (loadError) {
      setError(loadError.message);
    }
  };

  useEffect(() => {
    load();
    api
      .weather()
      .then((body) => {
        if (body.city) setCity(body.city);
      })
      .catch(() => {});
  }, []);

  const pickBody = async (event) => {
    const file = event.target.files?.[0];
    if (!file) return;
    setUploadingBody(true);
    setError("");
    try {
      const result = await api.upload(file);
      update({ photo_full: result.path });
      setBodyPreview(result.url);
      setMessage("照片已上传，点下面的「保存」才会生效。");
    } catch (uploadError) {
      setError(uploadError.message);
    } finally {
      setUploadingBody(false);
    }
  };

  const saveCity = async () => {
    const name = city.trim();
    if (!name) return;
    setSavingCity(true);
    setCityMessage("");
    try {
      const body = await api.setCity(name);
      setCity(body.city.split("·").pop());
      setCityMessage(`已设为 ${body.city}，首页会自动取温度了。`);
    } catch (cityError) {
      setCityMessage(cityError.message);
    } finally {
      setSavingCity(false);
    }
  };

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
        photo_full: form.photo_full || null,
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

      <section className="card p-5">
        <p className="text-xs uppercase tracking-[0.2em] text-muted">城市</p>
        <p className="mt-2 text-xs leading-relaxed text-muted">
          用来取当天温度。不设也能用，只是每天早上要自己调温度。
        </p>
        <div className="mt-3 flex gap-2">
          <input
            className="field flex-1"
            value={city}
            onChange={(event) => setCity(event.target.value)}
            placeholder="杭州"
          />
          <button type="button" className="btn" onClick={saveCity} disabled={savingCity}>
            {savingCity ? "…" : "设定"}
          </button>
        </div>
        {cityMessage ? <p className="mt-2 text-xs text-brass">{cityMessage}</p> : null}
      </section>

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
        <p className="text-xs uppercase tracking-[0.2em] text-muted">身体照片</p>
        <p className="mt-2 text-xs leading-relaxed text-muted">
          出试穿图要用它。不传也能用——只是看不到"你穿着这套"的样子。
        </p>

        <label className="mt-3 block">
          <div className="flex h-56 items-center justify-center overflow-hidden rounded-xl border border-edge bg-ink">
            {bodyPreview ? (
              <img src={bodyPreview} alt="身体照片" className="h-full w-full object-contain" />
            ) : (
              <span className="text-sm text-muted">
                {uploadingBody ? "上传中……" : "点这里选一张全身照"}
              </span>
            )}
          </div>
          <input type="file" accept="image/*" className="sr-only" onChange={pickBody} />
        </label>

        <ul className="mt-3 space-y-2 text-sm leading-relaxed text-muted">
          <li>· 白墙前，正对窗，不要逆光也不要开美颜</li>
          <li>· 手机架在胸口高度，拍全身，脚背要拍到</li>
          <li>· 穿深色贴身背心＋短裤，别穿宽松衣服</li>
          <li>· 一张就够，比多拍十张有用的是把三围量准</li>
        </ul>
        <p className="mt-3 text-[11px] leading-relaxed text-muted/70">
          不建议拍裸照：多数图像模型对裸露图像有安全过滤会直接拒图，贴身衣物反而更容易看出肩线和腿长，而且泄露代价完全不同。
        </p>
      </section>
    </div>
  );
}
