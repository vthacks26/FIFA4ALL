/**
 * Webcam view with the reticle overlaid.
 *
 * Video comes from the Python bridge as MJPEG rather than getUserMedia, because
 * the tracking process already owns the camera.
 *
 * This component owns the coordinate mapping. Landmarks arrive normalized to
 * the source image, but the video is drawn with `object-fit: cover`, so it is
 * scaled up and cropped to fill the frame. Without undoing that crop the ball
 * lands in the middle of the frame instead of on the user's nose.
 */

import { useEffect, useRef, useState } from "react";

import type { ControlState, Thresholds } from "../types";
import { BRIDGE_URL } from "../control/source";
import { Reticle, type ReticleMapping } from "./Reticle";
import "./CameraFrame.css";

/** Nose offset, in normalized units, spanning half the frame when no video. */
const SIMULATED_RANGE = 0.17;

interface Size {
  readonly width: number;
  readonly height: number;
}

interface CameraFrameProps {
  readonly state: ControlState;
  readonly thresholds: Thresholds;
  readonly hasVideo: boolean;
  readonly size?: number;
  readonly lockProgress?: number;
  readonly locked?: boolean;
  readonly showKeys?: boolean;
  readonly label?: string;
}

export function CameraFrame({
  state,
  thresholds,
  hasVideo,
  size = 300,
  lockProgress = 0,
  locked = false,
  showKeys = true,
  label,
}: CameraFrameProps) {
  const viewRef = useRef<HTMLDivElement>(null);
  const [view, setView] = useState<Size | null>(null);
  const [video, setVideo] = useState<Size | null>(null);

  // The frame is sized from props but also flexes, so measure it for real.
  useEffect(() => {
    const element = viewRef.current;
    if (element === null) return;
    const measure = () =>
      setView({ width: element.clientWidth, height: element.clientHeight });
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  const mapping = buildMapping(view, hasVideo ? video : null, state, thresholds);

  return (
    <div className="camera" style={{ width: size }}>
      <div className="camera__view" ref={viewRef} style={{ height: size * 1.18 }}>
        {hasVideo ? (
          <img
            className="camera__video"
            src={`${BRIDGE_URL}/stream.mjpg`}
            alt=""
            onLoad={(event) => {
              const image = event.currentTarget;
              if (image.naturalWidth > 0) {
                setVideo({ width: image.naturalWidth, height: image.naturalHeight });
              }
            }}
          />
        ) : (
          <div className="camera__placeholder">
            <span>SIMULATED INPUT</span>
          </div>
        )}

        {mapping !== null && (
          <div className="camera__overlay">
            <Reticle
              state={state}
              thresholds={thresholds}
              mapping={mapping}
              lockProgress={lockProgress}
              locked={locked}
              showKeys={showKeys}
            />
          </div>
        )}

        <div className={`camera__status ${state.tracking ? "is-ok" : ""}`}>
          {state.tracking ? "FACE TRACKED" : "NO FACE"}
        </div>
      </div>
      {label !== undefined && <p className="camera__label">{label}</p>}
    </div>
  );
}

/**
 * Map normalized landmark coordinates into pixels inside the frame.
 *
 * With video, this undoes the `object-fit: cover` scale and crop. Without it,
 * neutral sits at the centre of the frame and a synthetic scale keeps the zone
 * graphic a sensible size.
 */
function buildMapping(
  view: Size | null,
  video: Size | null,
  state: ControlState,
  thresholds: Thresholds,
): ReticleMapping | null {
  if (view === null || view.width === 0 || view.height === 0) return null;

  // Control space pre-multiplies y, so scaleY divides it back out.
  const toControl = (scale: number) => scale / thresholds.y_scale;

  if (video === null || video.width === 0 || video.height === 0) {
    const pxPerUnit = view.width / (SIMULATED_RANGE * 2);
    const centreX = view.width / 2;
    const centreY = view.height / 2;
    return {
      width: view.width,
      height: view.height,
      anchorX: centreX,
      anchorY: centreY,
      ballX: centreX + state.nose.x * pxPerUnit,
      ballY: centreY + state.nose.y * pxPerUnit * thresholds.y_scale,
      scaleX: pxPerUnit,
      scaleY: toControl(pxPerUnit),
    };
  }

  const scale = Math.max(view.width / video.width, view.height / video.height);
  const renderedWidth = video.width * scale;
  const renderedHeight = video.height * scale;
  const offsetX = (view.width - renderedWidth) / 2;
  const offsetY = (view.height - renderedHeight) / 2;
  const toPixels = (x: number, y: number) => ({
    x: offsetX + x * renderedWidth,
    y: offsetY + y * renderedHeight,
  });

  // Fall back to the frame centre until calibration has run.
  const centre = state.center_point ?? { x: 0.5, y: 0.5 };
  const anchor = toPixels(centre.x, centre.y);
  const nose = state.nose_point ?? centre;
  const ball = toPixels(nose.x, nose.y);

  return {
    width: view.width,
    height: view.height,
    anchorX: anchor.x,
    anchorY: anchor.y,
    ballX: ball.x,
    ballY: ball.y,
    scaleX: renderedWidth,
    scaleY: toControl(renderedHeight),
  };
}
