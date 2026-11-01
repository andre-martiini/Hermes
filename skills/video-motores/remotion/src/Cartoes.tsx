import React from "react";
import { AbsoluteFill, Easing, interpolate, Sequence, spring, useCurrentFrame, useVideoConfig } from "remotion";

// Mesma paleta e mesmo roteiro da versão HyperFrames, para comparar só o motor.
const C = { ground: "#0f172a", ink: "#e2e8f0", muted: "#94a3b8", accent: "#f59e0b", box: "#1e293b" };
const FONT = '"Segoe UI", system-ui, sans-serif';
const ENTRA = Easing.bezier(0.16, 1, 0.3, 1);

const useEntra = (inicio: number, dur = 0.45) => {
  const f = useCurrentFrame();
  const { fps } = useVideoConfig();
  return interpolate(f, [inicio * fps, (inicio + dur) * fps], [0, 1], {
    easing: ENTRA, extrapolateLeft: "clamp", extrapolateRight: "clamp",
  });
};

const Sai: React.FC<{ em: number; children: React.ReactNode }> = ({ em, children }) => {
  const f = useCurrentFrame();
  const { fps } = useVideoConfig();
  const o = interpolate(f, [em * fps, (em + 0.3) * fps], [1, 0], {
    easing: Easing.in(Easing.quad), extrapolateLeft: "clamp", extrapolateRight: "clamp",
  });
  return (
    <AbsoluteFill style={{ opacity: o, padding: "288px 90px 384px", display: "flex", flexDirection: "column",
      justifyContent: "center", gap: 56, fontFamily: FONT, color: C.ink }}>
      {children}
    </AbsoluteFill>
  );
};

const Sobe: React.FC<{ inicio: number; dx?: number; dy?: number; style?: React.CSSProperties; children: React.ReactNode }> =
  ({ inicio, dx = 0, dy = 60, style, children }) => {
    const u = useEntra(inicio);
    return <div style={{ opacity: u, transform: `translate(${(1 - u) * dx}px, ${(1 - u) * dy}px)`, ...style }}>{children}</div>;
  };

const etiqueta: React.CSSProperties = { color: C.accent, fontSize: 40, fontWeight: 700, letterSpacing: "0.12em", textTransform: "uppercase" };
const h2: React.CSSProperties = { fontSize: 76, fontWeight: 700, lineHeight: 1.1, letterSpacing: "-0.02em" };
const caixa: React.CSSProperties = { display: "flex", alignItems: "center", gap: 36, background: C.box, borderRadius: 28, padding: "40px 44px" };

const Numero = () => {
  const f = useCurrentFrame();
  const { fps } = useVideoConfig();
  const v = interpolate(f, [0.5 * fps, 2.7 * fps], [0, 1250000], {
    easing: Easing.out(Easing.cubic), extrapolateLeft: "clamp", extrapolateRight: "clamp",
  });
  return (
    <Sai em={4.7}>
      <div style={etiqueta}>Prestação de contas</div>
      <div style={h2}>Recurso executado em 2026</div>
      <Sobe inicio={0.1} style={{ fontSize: 150, fontWeight: 800, color: C.accent, fontVariantNumeric: "tabular-nums", letterSpacing: "-0.03em" }}>
        R$ {Math.round(v).toLocaleString("pt-BR")}
      </Sobe>
      <Sobe inicio={0.16} style={{ fontSize: 48, color: C.muted }}>valores fictícios</Sobe>
    </Sai>
  );
};

const Ranking = () => {
  const f = useCurrentFrame();
  const { fps } = useVideoConfig();
  const pulso = 1 + 0.12 * spring({ frame: f - 2.2 * fps, fps, config: { damping: 8 }, durationInFrames: 12 }) *
    (1 - spring({ frame: f - 2.6 * fps, fps, config: { damping: 200 } }));
  const itens: [string, string][] = [["Assistência estudantil", "42%"], ["Pesquisa", "31%"], ["Extensão", "18%"]];
  return (
    <Sai em={4.7}>
      <Sobe inicio={0.1} style={etiqueta}>Ranking</Sobe>
      <Sobe inicio={0.16} style={h2}>Onde o recurso foi aplicado</Sobe>
      {itens.map(([nome, pct], i) => (
        <Sobe key={nome} inicio={0.6 + i * 0.5} dx={-120} dy={0} style={caixa}>
          <div style={{ width: 96, height: 96, borderRadius: "50%", background: C.accent, color: C.ground, fontSize: 56,
            fontWeight: 800, display: "grid", placeItems: "center", flex: "none", transform: `scale(${i === 0 ? pulso : 1})` }}>{i + 1}</div>
          <div style={{ fontSize: 52, fontWeight: 600, flex: 1 }}>{nome}</div>
          <div style={{ fontSize: 56, fontWeight: 800, color: C.accent, fontVariantNumeric: "tabular-nums" }}>{pct}</div>
        </Sobe>
      ))}
    </Sai>
  );
};

const Fluxo = () => {
  const f = useCurrentFrame();
  const { fps } = useVideoConfig();
  const etapas = ["Demanda", "Planejamento", "Licitação", "Contrato"];
  return (
    <Sai em={4.7}>
      <Sobe inicio={0.1} style={etiqueta}>Fluxo</Sobe>
      <Sobe inicio={0.16} style={h2}>Da demanda ao contrato</Sobe>
      {etapas.map((e, i) => {
        const ativa = f >= (1.6 + i * 0.7) * fps;
        return (
          <React.Fragment key={e}>
            {i > 0 && <Sobe inicio={0.5 + (i * 2 - 1) * 0.25} dy={40}
              style={{ height: 40, width: 6, background: C.muted, marginLeft: 74, opacity: 0.5 }}>{null}</Sobe>}
            <Sobe inicio={0.5 + i * 2 * 0.25} dy={40}
              style={{ ...caixa, padding: "36px 44px", border: `4px solid ${ativa ? C.accent : "transparent"}` }}>
              <div style={{ fontSize: 48, fontWeight: 800, color: C.muted, width: 64 }}>{i + 1}</div>
              <div style={{ fontSize: 54, fontWeight: 600 }}>{e}</div>
            </Sobe>
          </React.Fragment>
        );
      })}
    </Sai>
  );
};

export const Cartoes = () => (
  <AbsoluteFill style={{ background: C.ground }}>
    <Sequence durationInFrames={150}><Numero /></Sequence>
    <Sequence from={150} durationInFrames={150}><Ranking /></Sequence>
    <Sequence from={300} durationInFrames={150}><Fluxo /></Sequence>
  </AbsoluteFill>
);
