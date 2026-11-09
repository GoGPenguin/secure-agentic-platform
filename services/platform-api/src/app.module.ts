import { Module } from '@nestjs/common';
import { InfoModule } from './info/info.module.js';
import { HealthModule } from './health/health.module.js';

@Module({
  imports: [InfoModule, HealthModule],
})
export class AppModule {}
