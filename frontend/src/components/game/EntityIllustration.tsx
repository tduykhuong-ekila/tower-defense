import { useState } from "react";
import { Shield, Swords } from "lucide-react";
import { entityArtwork } from "../../game/entityArtwork";

interface Props { code: string; name: string; category: string; teamIndex?: number; level?: number; }

export function EntityIllustration({ code, name, category, teamIndex = 0, level = 1 }: Props) {
  const source = entityArtwork(code, teamIndex, level);
  const [loaded, setLoaded] = useState<string>();
  const [failed, setFailed] = useState<string>();
  const ready = !!source && loaded === source && failed !== source;
  return <span className="entity-illustration" data-state={ready ? "ready" : source && failed !== source ? "loading" : "fallback"}>
    {!ready && <span className="entity-art-placeholder" role="img" aria-label={`${name} · ${source && failed !== source ? "Đang tải hình" : "Chưa có hình minh họa"}`}>
      {category === "TOWER" ? <Shield size={36} /> : <Swords size={36} />}
    </span>}
    {source && failed !== source && <img src={source} alt={name} width="160" height="112"
      decoding="async" style={{ opacity: ready ? 1 : 0 }}
      onLoad={() => setLoaded(source)} onError={() => setFailed(source)} />}
  </span>;
}
