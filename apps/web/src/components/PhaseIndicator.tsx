import type { ScenePhase } from '../types/generated';

interface PhaseIndicatorProps {
  phase: ScenePhase;
}

const phaseLabels: Record<ScenePhase, string> = {
  scene_intro: 'Scene Intro',
  discussion: 'Discussion',
  action_commit: 'Action',
  resolution: 'Resolution',
  narration: 'Narration',
  reaction: 'Reaction',
  turn_end: 'Turn End',
};

export default function PhaseIndicator({ phase }: PhaseIndicatorProps) {
  const label = phaseLabels[phase] ?? phase;
  const phaseClass = phase.replace('_', '-');

  return (
    <span className={`phase-indicator phase-${phaseClass}`}>
      {label}
    </span>
  );
}
