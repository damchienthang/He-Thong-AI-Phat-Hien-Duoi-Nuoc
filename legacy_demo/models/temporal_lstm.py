import torch
from torch import nn
from config.settings import CLASSES

class TemporalLSTM(nn.Module):
    def __init__(self, hidden_size=64, num_layers=1, num_classes=3):
        super().__init__()
        self.lstm = nn.LSTM(34,hidden_size,num_layers,batch_first=True)
        self.fc = nn.Linear(hidden_size,num_classes)

    def forward(self, x):
        if x.ndim != 4 or tuple(x.shape[-2:]) != (17,2):
            raise ValueError('Input cần shape (batch, sequence, 17, 2).')
        output,_ = self.lstm(x.flatten(2))
        return self.fc(output[:,-1])

def create_demo_checkpoint(path, sequence_length=30):
    with torch.random.fork_rng():
        torch.manual_seed(42)
        model = TemporalLSTM()
    torch.save(dict(format_version=1,architecture='TemporalLSTM',hidden_size=64,num_layers=1,
                    num_classes=3,sequence_length=sequence_length,keypoints=17,coordinates=2,
                    normalization='frame_xy_0_1',classes=list(CLASSES),trained=False,
                    state_dict=model.state_dict()),path)
