# gpu_usage.py
from pynvml import nvmlInit, nvmlDeviceGetHandleByIndex, nvmlDeviceGetUtilizationRates

class GpuUsage:
    def __init__(self):
        nvmlInit()
        # Por simplicidade, assumindo apenas 1 GPU (índice 0).
        # Ajuste se tiver múltiplas GPUs ou quiser somar.
        self.handle = nvmlDeviceGetHandleByIndex(0)

    def get_gpu_utilization(self):
        """Retorna a % de uso de GPU."""
        utilization = nvmlDeviceGetUtilizationRates(self.handle)
        return utilization.gpu  # ou utilization.mem para uso de memória
