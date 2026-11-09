import { Module } from '@nestjs/common';
import { AppController } from './app.controller.js';
import { AppService } from './app.service.js';
import { InfoModule } from './info/info.module.js';
import { HealthModule } from './health/health.module.js';

@Module({
  imports: [InfoModule, HealthModule],
  controllers: [AppController],
  providers: [AppService],
})
export class AppModule {}
