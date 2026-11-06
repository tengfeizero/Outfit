import { useEffect, useState } from "react";
import { api, CATEGORY_LABELS } from "../api.js";

const TODAY = new Date().toLocaleDateString("zh-CN", {
  month: "long",
  day: "numeric",
  weekday: "long",
});

function Swatch({ color, small = false }) {
  const size = small ? "h-6 w-6" : "h-9 w-9";
  return (
    <span
      className={`${size} shrink-0 rounded-full border border-white/10`}
      style={{ backgroundColor: color || "#3A3A3A" }}
    />
  );
}

function PlanCard({ plan, index, onSaved, onWorn }) {
  const [busy, setBusy] = useState(false);
  const [savedId, setSavedId] = useState(null);
  const [image, setImage] = useState(null);
  const [note, setNote] = useState("");
  const [rendering, setRendering] = useState(false);

  const showBoard = async () => {
    setRendering(true);
    setNote("");
    try {
      const result = await api.render({
        garment_ids: plan.garment_ids,
        title: `${plan.occasion_label || ""} · ${plan.label}`.trim(),
        subtitle: `${Math.round(plan.temp_c || 0)}℃`,
        rationale: plan.rationale,
      });
      setImage(result.url);
      setNote(result.note || "");
    } catch (renderError) {
      setNote(renderError.message);
    } finally {
      setRendering(false);
    }
  };

  const save = async () => {
    setBusy(true);
    try {
      const result = await api.saveOutfit({
        occasion: plan.occasion,
        temp_c: plan.temp_c,
        garment_ids: plan.garment_ids,
        rationale: plan.rationale,
      });
      setSavedId(result.id);
      onSaved?.(index, result.id);
    } catch (error) {
      alert(error.message);
    } finally {
      setBusy(false);
    }
  };

  const wear = async () => {
    if (!savedId) {
      await save();
      return;
    }
    setBusy(true);
    try {
      await api.markWorn(savedId);
      onWorn?.();
    } catch (error) {
      alert(error.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <article className="card overflow-hidden">
      <header className="flex items-center justify-between border-b border-edge px-5 py-3">
        <span className="text-xs tracking-[0.2em] text-brass">{plan.label}</span>
        <span className="text-xs text-muted">评分 {plan.score.toFixed(2)}</span>
      </header>

      <ul className="divide-y divide-edge/60 px-5">
        {plan.items.map((item) => (
          <li key={`${item.id}-${item.category}`} className="flex items-center gap-3 py-3">
            <Swatch color={item.color_hex} />
            <div className="min-w-0 flex-1">
              <p className="truncate text-sm">{item.name}</p>
              <p className="text-xs text-muted">
                {CATEGORY_LABELS[item.category] || item.category} · {item.color_primary}
                {item.material ? ` · ${item.material}` : ""}
              </p>
            </div>
          </li>
        ))}
      </ul>

      <p className="px-5 pb-4 pt-3 text-sm leading-relaxed text-muted">{plan.rationale}</p>

      {image ? (
        <div className="border-t border-edge bg-black/20">
          <img src={image} alt="搭配图" className="w-full" />
          {note ? <p className="px-5 pb-3 pt-2 text-[11px] leading-relaxed text-muted/70">{note}</p> : null}
        </div>
      ) : null}

      <div className="border-t border-edge px-5 py-4">
        <button className="btn w-full" onClick={showBoard} disabled={rendering}>
          {rendering ? "在拼……" : image ? "重做这张图" : "看搭配图"}
        </button>
        <div className="mt-2 flex gap-2">
          <button className="btn-ghost flex-1" onClick={save} disabled={busy || savedId}>
            {savedId ? "已收藏" : "收藏"}
          </button>
          <button className="btn-ghost flex-1" onClick={wear} disabled={busy}>
            今天就穿这套
          </button>
        </div>
      </div>
    </article>
  );
}

export default function Today({ status }) {
  const [occasions, setOccasions] = useState([]);
  const [occasion, setOccasion] = useState("work");
  const [temp, setTemp] = useState(18);
  const [weather, setWeather] = useState(null);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  useEffect(() => {
    api.occasions().then((body) => setOccasions(body.occasions)).catch(() => {});
  }, []);

  useEffect(() => {
    api
      .weather()
      .then((body) => {
        setWeather(body);
        // 有天气就先把温度摆好，省得每天早上点加减号
        if (typeof body.temp_c === "number") setTemp(Math.round(body.temp_c));
      })
      .catch(() => setWeather({ configured: false, error: "取天气失败" }));
  }, []);

  const generate = async (excludeIds = []) => {
    setLoading(true);
    setError("");
    try {
      const body = await api.plan(occasion, temp);
      const label = occasions.find((item) => item.key === occasion)?.label || "";
      const plans = body.plans.map((plan) => ({
        ...plan,
        occasion,
        occasion_label: label,
        temp_c: temp,
      }));
      setData({ ...body, plans });
      if (excludeIds.length && plans.length) {
        const same =
          plans[0].garment_ids.length === excludeIds.length &&
          plans[0].garment_ids.every((id) => excludeIds.includes(id));
        setNotice(same ? "衣橱里能换的组合用完了，这就是不同的极限了。" : "");
      } else {
        setNotice("");
      }
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setLoading(false);
    }
  };

  const empty = status && status.garments === 0;

  let weatherHint = "";
  if (weather === null) {
    weatherHint = "在取天气……";
  } else if (weather.configured === false) {
    weatherHint = "还没设城市——去「我的」填一下，这里以后就是当天温度，不用手调。";
  } else if (typeof weather.temp_c === "number") {
    weatherHint =
      `${weather.city} · ${weather.summary} · 出门约 ${weather.temp_c}℃` +
      (weather.is_rainy ? " · 记得带伞" : "") +
      (weather.stale ? "（上次的数据）" : "");
  } else {
    weatherHint = weather.error || "没取到天气，手动调一下温度。";
  }

  return (
    <div className="space-y-6">
      <header>
        <p className="text-xs uppercase tracking-[0.3em] text-muted">{TODAY}</p>
        <h1 className="mt-2 text-3xl font-semibold tracking-tight">今天穿什么</h1>
        {status?.offline ? (
          <p className="mt-1 text-xs text-brass/80">离线模式 · 搭配可用，出图未接</p>
        ) : null}
      </header>

      {empty ? (
        <div className="card p-5">
          <p className="text-sm text-paper">衣橱还是空的。</p>
          <p className="mt-2 text-sm leading-relaxed text-muted">
            先去「入库」录几件衣服——上装、下装、鞋各来一件就能出第一套方案。
          </p>
        </div>
      ) : null}

      <section className="space-y-3">
        <p className="label">场合</p>
        <div className="flex flex-wrap gap-2">
          {occasions.map((item) => (
            <button
              key={item.key}
              onClick={() => setOccasion(item.key)}
              className={`chip ${occasion === item.key ? "chip-active" : ""}`}
            >
              {item.label}
            </button>
          ))}
        </div>
      </section>

      <section>
        <p className="label">外面多少度</p>
        <div className="card flex items-center justify-between px-5 py-4">
          <button
            className="text-2xl text-muted active:text-paper"
            onClick={() => setTemp((value) => value - 1)}
            aria-label="降低一度"
          >
            −
          </button>
          <div className="text-center">
            <span className="text-3xl font-medium tabular-nums">{temp}</span>
            <span className="ml-1 text-muted">℃</span>
          </div>
          <button
            className="text-2xl text-muted active:text-paper"
            onClick={() => setTemp((value) => value + 1)}
            aria-label="升高一度"
          >
            +
          </button>
        </div>
        <p className="mt-2 text-[11px] leading-relaxed text-muted/70">{weatherHint}</p>
      </section>

      <button className="btn w-full" onClick={() => generate()} disabled={loading || empty}>
        {loading ? "在挑……" : "给我三套"}
      </button>

      {error ? <p className="text-sm text-red-400">{error}</p> : null}

      {data ? (
        <section className="space-y-4">
          <p className="text-sm text-muted">
            {data.band_label} · {data.advice}
          </p>

          {data.plans.length === 0 ? (
            <div className="card p-5">
              <p className="text-sm text-paper">这套天气下凑不出方案</p>
              <p className="mt-2 text-sm text-muted">{data.reason}</p>
            </div>
          ) : null}

          {data.plans.map((plan, index) => (
            <PlanCard
              key={`${plan.label}-${index}`}
              plan={plan}
              index={index}
              onWorn={() => setNotice("已记下今天穿了这套。")}
            />
          ))}

          {data.plans.length > 0 ? (
            <button
              className="btn-ghost w-full"
              onClick={() => generate(data.plans.flatMap((plan) => plan.garment_ids))}
              disabled={loading}
            >
              都不满意，换一套
            </button>
          ) : null}

          {notice ? <p className="text-center text-xs text-muted">{notice}</p> : null}
        </section>
      ) : null}
    </div>
  );
}
