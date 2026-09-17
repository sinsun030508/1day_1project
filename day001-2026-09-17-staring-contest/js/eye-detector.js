// MediaPipe Face Landmarker로 눈 감김 정도(0~1)를 읽는다. 영상은 브라우저 안에서만 처리된다.
import {
  FaceLandmarker,
  FilesetResolver,
} from "https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@1.0.1/vision_bundle.mjs";

const WASM_URL = "https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@1.0.1/wasm";
const MODEL_URL =
  "https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task";

export class EyeDetector {
  #landmarker = null;
  #video = null;
  #lastTs = -1;

  async init(video) {
    this.#video = video;
    const fileset = await FilesetResolver.forVisionTasks(WASM_URL);
    const options = (delegate) => ({
      baseOptions: { modelAssetPath: MODEL_URL, delegate },
      runningMode: "VIDEO",
      numFaces: 1,
      outputFaceBlendshapes: true,
    });
    try {
      this.#landmarker = await FaceLandmarker.createFromOptions(fileset, options("GPU"));
    } catch {
      this.#landmarker = await FaceLandmarker.createFromOptions(fileset, options("CPU"));
    }
  }

  /** @returns {{face: boolean, blink: number}} blink: 양쪽 눈 감김 점수 평균 (0=뜸, 1=감음) */
  read() {
    const video = this.#video;
    if (!this.#landmarker || video.readyState < 2) return { face: false, blink: 0 };

    let ts = performance.now();
    if (ts <= this.#lastTs) ts = this.#lastTs + 1;
    this.#lastTs = ts;

    const result = this.#landmarker.detectForVideo(video, ts);
    const shapes = result.faceBlendshapes?.[0]?.categories;
    if (!shapes) return { face: false, blink: 0 };

    const score = (name) => shapes.find((c) => c.categoryName === name)?.score ?? 0;
    const blink = (score("eyeBlinkLeft") + score("eyeBlinkRight")) / 2;
    return { face: true, blink };
  }
}
