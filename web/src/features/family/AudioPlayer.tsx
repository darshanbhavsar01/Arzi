/** "Listen": a large play button, a seekable progress bar and playback speed, for phones. */
import { Pause, Play } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';

import type { FamilyStrings } from '@/features/family/strings';

const SPEEDS = [0.75, 1, 1.25, 1.5] as const;

function clock(seconds: number): string {
  const s = Math.max(0, Math.floor(seconds));
  return `${String(Math.floor(s / 60))}:${String(s % 60).padStart(2, '0')}`;
}

export function AudioPlayer({
  src,
  seconds,
  t,
}: {
  src: string;
  seconds: number;
  t: FamilyStrings;
}) {
  const audio = useRef<HTMLAudioElement>(null);
  const [playing, setPlaying] = useState(false);
  const [position, setPosition] = useState(0);
  const [speed, setSpeed] = useState<(typeof SPEEDS)[number]>(1);

  useEffect(() => {
    if (audio.current) audio.current.playbackRate = speed;
  }, [speed, src]);

  function toggle() {
    const node = audio.current;
    if (!node) return;
    if (node.paused) void node.play();
    else node.pause();
  }

  return (
    <div className="flex items-center gap-4 rounded-2xl bg-navy p-4 text-white shadow-pop">
      {/* The narration reads exactly the text shown on this page, which serves as its transcript. */}
      {/* eslint-disable-next-line jsx-a11y/media-has-caption */}
      <audio
        ref={audio}
        src={src}
        preload="metadata"
        onPlay={() => {
          setPlaying(true);
        }}
        onPause={() => {
          setPlaying(false);
        }}
        onEnded={() => {
          setPlaying(false);
        }}
        onTimeUpdate={(e) => {
          setPosition(e.currentTarget.currentTime);
        }}
      />
      <button
        type="button"
        onClick={toggle}
        className="grid size-14 shrink-0 place-content-center rounded-full bg-accent text-white focus-visible:outline-white"
        aria-label={playing ? t.pause : t.listen}
      >
        {playing ? (
          <Pause className="size-6" aria-hidden />
        ) : (
          <Play className="ml-0.5 size-6" aria-hidden />
        )}
      </button>
      <div className="min-w-0 flex-1">
        <p className="text-base font-semibold">{playing ? t.pause : t.listen}</p>
        <input
          type="range"
          min={0}
          max={Math.max(seconds, 1)}
          step={0.5}
          value={position}
          aria-label={t.listen}
          aria-valuetext={`${clock(position)} / ${clock(seconds)}`}
          onChange={(e) => {
            const value = Number(e.target.value);
            if (audio.current) audio.current.currentTime = value;
            setPosition(value);
          }}
          className="mt-2 h-2 w-full cursor-pointer accent-accent"
        />
        <div className="mt-1 flex items-center justify-between text-xs text-white/80 tabular-nums">
          <span>
            {clock(position)} / {clock(seconds)}
          </span>
          <label className="flex items-center gap-1.5">
            {t.speed}
            <select
              value={speed}
              onChange={(e) => {
                setSpeed(Number(e.target.value) as (typeof SPEEDS)[number]);
              }}
              className="rounded bg-white/15 px-1.5 py-1 text-white"
            >
              {SPEEDS.map((s) => (
                <option key={s} value={s} className="text-ink">
                  {s}×
                </option>
              ))}
            </select>
          </label>
        </div>
      </div>
    </div>
  );
}
