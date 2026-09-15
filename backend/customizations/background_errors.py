SAFE_MESSAGE = "No pudimos separar el fondo de este diseño con suficiente precisión. Probá con una imagen de mayor calidad o con mayor contraste entre el diseño y el fondo."


class BackgroundRemovalBusy(Exception):
    pass


class BackgroundRemovalRejected(Exception):
    def __init__(self, reason, confidence=0.0, message=SAFE_MESSAGE):
        super().__init__(message)
        self.reason = reason
        self.confidence = float(confidence)


class SegmentationUnavailable(Exception):
    pass
