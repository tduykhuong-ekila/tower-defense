let context: AudioContext | null = null;
export function playFeedback(kind: "select" | "success" | "error") {
  try {
    context ||= new AudioContext();
    void context.resume();
    const oscillator = context.createOscillator(),
      gain = context.createGain();
    oscillator.connect(gain);
    gain.connect(context.destination);
    oscillator.type = "sine";
    oscillator.frequency.setValueAtTime(
      kind === "success" ? 660 : kind === "error" ? 180 : 440,
      context.currentTime,
    );
    oscillator.frequency.exponentialRampToValueAtTime(
      kind === "success" ? 880 : kind === "error" ? 120 : 550,
      context.currentTime + 0.12,
    );
    gain.gain.setValueAtTime(0.035, context.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.001, context.currentTime + 0.18);
    oscillator.start();
    oscillator.stop(context.currentTime + 0.2);
  } catch {
    /* Text and visual feedback are always available. */
  }
}
