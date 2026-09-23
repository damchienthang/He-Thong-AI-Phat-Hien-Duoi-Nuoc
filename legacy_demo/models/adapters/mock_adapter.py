from models.adapters.base import BasePredictor, Prediction

class MockPredictor(BasePredictor):
    """Scripted whole-frame predictions, never person detection."""
    is_demo = True
    name = 'Scripted frame demo'
    def predict(self, frame, timestamp):
        phase = timestamp % 20
        label = 'swimming' if phase < 4 else 'drowning' if phase < 15 else 'out_of_water'
        return [Prediction(0, label, 0.92)]
