from strands.models import BedrockModel

from settings import settings

model = BedrockModel(model_id=settings.model_id, region_name=settings.region)
