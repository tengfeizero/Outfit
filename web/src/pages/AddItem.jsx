import { useState } from "react";
import { api } from "../api.js";

const CATEGORIES = [
  { key: "top", label: "上装" },
  { key: "bottom", label: "下装" },
  { key: "outerwear", label: "外套" },
  { key: "dress", label: "连衣裙" },
  { key: "shoes", label: "鞋" },
  { key: "bag", label: "包" },
  { key: "accessory", label: "配饰" },
];

const PALETTE = ["#F2F2F0", "#1A1A1A", "#8A8A8A", "#1F2A44", "#6E8CA8", "#D8CDB8", "#B08A5E", "#3A3A3A"];

const initial = {
  name: "",
  category: "top",
  color_primary: "黑",
  color_hex: "#1A1A1A",
  warmth: 3,
  formality: 3,
  material: "",
  image_path: null,
};

export default function AddItem({ onAdded }) {
  const [form, setForm] = useState(initial);
  const [preview, setPreview] = useState(null);
  const [uploading, setUploading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  const update = (patch) => setForm((value) => ({ ...value, ...patch }));

  const pickFile = async (event) => {
    const file = event.target.files?.[0];
    if (!file) return;
    setUploading(true);
    setError("");
    try {
      const result = await api.upload(file);
      update({ image_path: result.path });
      setPreview(result.url);
    } catch (uploadError) {
      setError(uploadError.message);
    } finally {
      setUploading(false);
    }
  };

  const submit = async (event) => {
    event.preventDefault();
    if (!form.name.trim()) {
      setError("先给它起个名字，比如「黑羊毛针织」。");
      return;
    }
    setSaving(true);
    setError("");
    try {
      await api.createGarment({
        ...form,
        name: form.name.trim(),
        material: form.material.trim() || null,
        label_confidence: 1.0,
      });
      setForm(initial);
      setPreview(null);
      onAdded?.();
    } catch (saveError) {
      setError(saveError.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <form className="space-y-6" onSubmit={submit}>
      <header>
        <h1 className="text-3xl font-semibold tracking-tight">入库</h1>
        <p className="mt-1 text-sm text-muted">
          先手填。自动抠图和自动打标在下一步接，那之后你只要拍一张。
        </p>
      </header>

      <label className="block">
        <span className="label">照片</span>
        <div className="card flex h-40 items-center justify-center overflow-hidden">
          {preview ? (
            <img src={preview} alt="预览" className="h-full w-full object-cover" />
          ) : (
            <span className="text-sm text-muted">{uploading ? "上传中……" : "点这里选一张"}</span>
          )}
        </div>
        <input type="file" accept="image/*" className="sr-only" onChange={pickFile} />
      </label>

      <label className="block">
        <span className="label">名称</span>
        <input
          className="field"
          value={form.name}
          onChange={(event) => update({ name: event.target.value })}
          placeholder="黑羊毛针织"
        />
      </label>

      <div>
        <span className="label">品类</span>
        <div className="flex flex-wrap gap-2">
          {CATEGORIES.map((item) => (
            <button
              type="button"
              key={item.key}
              onClick={() => update({ category: item.key })}
              className={`chip ${form.category === item.key ? "chip-active" : ""}`}
            >
              {item.label}
            </button>
          ))}
        </div>
      </div>

      <div>
        <span className="label">主色</span>
        <div className="flex items-center gap-2">
          <input
            className="field flex-1"
            value={form.color_primary}
            onChange={(event) => update({ color_primary: event.target.value })}
            placeholder="藏蓝"
          />
          <input
            type="color"
            value={form.color_hex}
            onChange={(event) => update({ color_hex: event.target.value })}
            className="h-12 w-12 rounded-xl border border-edge bg-ink"
          />
        </div>
        <div className="mt-2 flex gap-2">
          {PALETTE.map((color) => (
            <button
              type="button"
              key={color}
              onClick={() => update({ color_hex: color })}
              className="h-7 w-7 rounded-full border border-white/15"
              style={{ backgroundColor: color }}
              aria-label={color}
            />
          ))}
        </div>
      </div>

      <label className="block">
        <span className="label">
          厚薄 <span className="text-paper">{form.warmth}</span> / 5
        </span>
        <input
          type="range"
          min="1"
          max="5"
          value={form.warmth}
          onChange={(event) => update({ warmth: Number(event.target.value) })}
          className="w-full accent-brass"
        />
        <span className="mt-1 flex justify-between text-[11px] text-muted">
          <span>1 最薄（短袖）</span>
          <span>5 最厚（大衣）</span>
        </span>
      </label>

      <label className="block">
        <span className="label">
          正式度 <span className="text-paper">{form.formality}</span> / 5
        </span>
        <input
          type="range"
          min="1"
          max="5"
          value={form.formality}
          onChange={(event) => update({ formality: Number(event.target.value) })}
          className="w-full accent-brass"
        />
        <span className="mt-1 flex justify-between text-[11px] text-muted">
          <span>1 睡衣</span>
          <span>5 礼服</span>
        </span>
      </label>

      <label className="block">
        <span className="label">材质（可留空）</span>
        <input
          className="field"
          value={form.material}
          onChange={(event) => update({ material: event.target.value })}
          placeholder="羊毛"
        />
      </label>

      {error ? <p className="text-sm text-red-400">{error}</p> : null}

      <button className="btn w-full" type="submit" disabled={saving}>
        {saving ? "在存……" : "存进衣橱"}
      </button>
    </form>
  );
}
