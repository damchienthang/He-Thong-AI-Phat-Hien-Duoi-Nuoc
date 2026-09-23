from collections import deque
import numpy as np

class PersonBuffers:
    """Only consecutive, observed poses; an absent/invalid pose discards history."""
    def __init__(self, length=30):
        self.length = length
        self.buffers = {}
        self.last_frame = {}

    def update(self, observations, frame_index):
        valid = {}
        for identity, pose in observations.items():
            pose = np.asarray(pose, dtype=np.float32)
            if pose.shape == (17,2) and np.isfinite(pose).all() and ((pose >= 0) & (pose <= 1)).all():
                valid[identity] = pose
        for identity in list(self.buffers):
            if identity not in valid or self.last_frame[identity] != frame_index-1:
                del self.buffers[identity]
                del self.last_frame[identity]
        ready = {}
        for identity,pose in valid.items():
            buffer = self.buffers.setdefault(identity,deque(maxlen=self.length))
            buffer.append(pose.copy())
            self.last_frame[identity] = frame_index
            if len(buffer) == self.length:
                ready[identity] = np.stack(buffer)
        return ready
