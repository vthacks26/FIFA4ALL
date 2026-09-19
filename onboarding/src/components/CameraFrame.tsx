/**
 * Webcam view with the reticle overlaid.
 *
 * Video comes from the Python bridge as MJPEG rather than getUserMedia, because
 * the tracking process already owns the camera. When no video is available the
 * frame degrades to a labelled placeholder so every screen still works.
 */

import type { ControlState, Thresholds } from "../types";
import { BRIDGE_URL } from "../control/source";
import { Reticle } from "./Reticle";
import "./CameraFrame.css";

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
  return (
    <div className="camera" style={{ width: size }}>
      <div className="camera__view" style={{ height: size * 1.18 }}>
        {hasVideo ? (
          <img className="camera__video" src={`${BRIDGE_URL}/stream.mjpg`} alt="" />
        ) : (
          <div className="camera__placeholder">
            <span>SIMULATED INPUT</span>
          </div>
        )}
        <div className="camera__overlay">
          <Reticle
            state={state}
            thresholds={thresholds}
            size={size * 0.82}
            lockProgress={lockProgress}
            locked={locked}
            showKeys={showKeys}
          />
        </div>
        <div className={`camera__status ${state.tracking ? "is-ok" : ""}`}>
          {state.tracking ? "FACE TRACKED" : "NO FACE"}
        </div>
      </div>
      {label !== undefined && <p className="camera__label">{label}</p>}
    </div>
  );
}
