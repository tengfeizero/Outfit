import { useState } from "react";
import { api, CATEGORY_LABELS } from "../api.js";

const CATEGORIES = [
  { key: "top", label: "上装" },
  { key: "bottom", label: "下装" },
  { key: "outerwear", label: "外套" },
  { key: "dress", label: "连衣裙" },
  { key: "shoes", label: "鞋" },
  { key: "bag", label: "包" },
  { key: "accessory", label: "配饰" },
];

const VERDICT_STYLE = {
  buy: { label: "值得买", tone: "text-brass", ring: "border-brass/50" },
  skip: { label: "不必买", tone: "text-paper", ring: "border-edge" },
  depends: { label: "看价格", tone: "text-paper", ring: "border-edge" },
};

export default function Shopping() {
  const [category, setCategory] = useState("top");
  const [formality, setFormality] = useState(3);
  const [photo, setPhoto] = useState(null);
  const [color, setColor] = useState({ hex: null, name: "未标注" });
  const [uploading, setUploading] = useState(false);
  const [loading, setLoading] = useState(false);
  const [verdict, setVerdict] = useState(null);
  const [error, setError] = useState("");

  const pickFile = async (event) => {
    const file = event.target.files?.[0];
    if (!file) return;
    setUploading(true);
    setError("");
    setVerdict(null);
    try {
      const result = await api.upload(file);
      setPhoto(result.cutout_url || result.url);
      setColor({ hex: result.color_hex, name: result.color_name });
    } catch (uploadError) {
      setError(uploadError.message);
    } finally {
      setUploading(false);
    }
  };

  const judge = async () => {
    setLoading(true);
    setError("");
    try {
      const result = await api.shopping({
        category,
        color_hex: color.hex,
        color_primary: color.name,
        formality,
        warmth: 3,
      });
      setVerdict(result);
    } catch (judgeError) {
      setError(judgeError.message);
    } finally {
      setLoading(false);
    }
  };

  const style = verdict ? VERDICT_STYLE[verdict.verdict] || VERDICT_STYLE.depends : null;

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-3xl font-semibold tracking-tight">买不买</h1>
        <p className="mt-1 text-sm text-muted">
          拍一件在店里看到的衣服，看看它能不能搭进你已有的衣橱。不是替你决定，是把账算给你看。
        </p>
      </header>

      <label className="block">
        <span className="label">照片</span>
        <div className="card flex h-40 items-center justify-center overflow-hidden">
          {photo ? (
            <img src={photo} alt="预览" className="h-full w-full object-contain" />
          ) : (
            <span className="text-sm text-muted">{uploading ? "上传中……" : "点这里选一张"}</span>
          )}
        </div>
        <input type="file" accept="image/*" className="sr-only" onChange={pickFile} />
      </label>

      <div>
        <span className="label">品类</span>
        <div className="flex flex-wrap gap-2">
          {CATEGORIES.map((item) => (
            <button
              key={item.key}
              onClick={() => setCategory(item.key)}
              className={`chip ${category === item.key ? "chip-active" : ""}`}
            >
              {item.label}
            </button>
          ))}
        </div>
      </div>

      <div>
        <span className="label">主色</span>
        <div className="card flex items-center gap-3 px-5 py-4">
          <span
            className="h-9 w-9 rounded-full border border-white/15"
            style={{ backgroundColor: color.hex || "#3A3A3A" }}
          />
          <span className="text-sm">{color.name}</span>
          <span className="ml-auto text-xs text-muted">{color.hex || "没拍照"}</span>
        </div>
      </div>

      <label className="block">
        <span className="label">
          正式度 <span className="text-paper">{formality}</span> / 5
        </span>
        <input
          type="range"
          min="1"
          max="5"
          value={formality}
          onChange={(event) => setFormality(Number(event.target.value))}
          className="w-full accent-brass"
        />
      </label>

      {error ? <p className="text-sm text-red-400">{error}</p> : null}

      <button className="btn w-full" onClick={judge} disabled={loading}>
        {loading ? "在算……" : "值不值得买"}
      </button>

      {verdict ? (
        <section className={`card border ${style.ring} p-5`}>
          <p className={`text-xs uppercase tracking-[0.25em] ${style.tone}`}>{style.label}</p>
          <p className="mt-2 text-xl leading-snug">{verdict.title}</p>

          <ul className="mt-4 space-y-2">
            {verdict.reasons.map((reason) => (
              <li key={reason} className="flex gap-2 text-sm leading-relaxed text-muted">
                <span className="text-brass">·</span>
                {reason}
              </li>
            ))}
          </ul>

          {verdict.pairs.length ? (
            <div className="mt-5">
              <p className="text-[11px] uppercase tracking-[0.2em] text-muted">能和这几件搭</p>
              <ul className="mt-2 divide-y divide-edge/60">
                {verdict.pairs.map((item) => (
                  <li key={item.id} className="flex items-center gap-3 py-2">
                    <span
                      className="h-6 w-6 shrink-0 rounded-full border border-white/10"
                      style={{ backgroundColor: item.color_hex || "#3A3A3A" }}
                    />
                    <span className="truncate text-sm">{item.name}</span>
                    <span className="ml-auto text-[11px] text-muted">
                      {CATEGORY_LABELS[item.category] || item.category}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
        </section>
      ) : null}

      <p className="text-[11px] leading-relaxed text-muted/70">
        判断依据只有三条：和你已有的重复不重复、能搭上几件、这个品类是不是空缺。不联网，也不猜你的喜好。
      </p>
    </div>
  );
}
