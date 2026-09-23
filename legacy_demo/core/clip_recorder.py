from collections import deque
import json
import cv2

class ClipRecorder:
    """JPEG pre-roll bounds RAM; post-roll streams to disk. Each frame is added once."""
    def __init__(self, fps, pre_seconds=2, post_seconds=2):
        self.fps = fps
        self.pre = deque(maxlen=max(1,round(pre_seconds*fps)))
        self.post_frames = max(1,round(post_seconds*fps))
        self.pending = []

    def push(self, frame):
        for item in self.pending[:]:
            item['writer'].write(frame)
            item['remaining'] -= 1
            item['written'] += 1
            if item['remaining'] == 0:
                self.finish(item,False)
        ok, encoded = cv2.imencode('.jpg',frame,[cv2.IMWRITE_JPEG_QUALITY,75])
        if ok:
            self.pre.append(encoded)

    def start(self, folder, size):
        writer = cv2.VideoWriter(str(folder/'clip.mp4'),cv2.VideoWriter_fourcc(*'mp4v'),self.fps,size)
        if not writer.isOpened():
            writer.release()
            self.metadata(folder,dict(clip_status='codec_unavailable'))
            return
        for encoded in self.pre:
            writer.write(cv2.imdecode(encoded,cv2.IMREAD_COLOR))
        self.pending.append(dict(writer=writer,folder=folder,remaining=self.post_frames,written=len(self.pre)))
        self.metadata(folder,dict(clip_status='recording'))

    def metadata(self,folder,changes):
        path = folder/'metadata.json'
        data = json.loads(path.read_text(encoding='utf-8'))
        data.update(changes)
        path.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')

    def finish(self,item,truncated):
        item['writer'].release()
        self.pending.remove(item)
        self.metadata(item['folder'],dict(clip_status='partial' if truncated else 'complete',clip_frames=item['written'],clip_fps=self.fps))

    def close(self):
        for item in self.pending[:]:
            self.finish(item,True)
        self.pre.clear()
