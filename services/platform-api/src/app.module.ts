import { Module } from '@nestjs/common';
import { InfoModule } from './info/info.module.js';
import { HealthModule } from './health/health.module.js';
import { MetricsModule } from './metrics/metrics.module.js';

@Module({
  imports: [MetricsModule, InfoModule, HealthModule],
})
export class AppModule {}
