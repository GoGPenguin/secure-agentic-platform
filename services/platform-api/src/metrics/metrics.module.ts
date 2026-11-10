import {
  Module,
  type MiddlewareConsumer,
  type NestModule,
} from '@nestjs/common';
import { HttpMetricsMiddleware } from './http-metrics.middleware.js';
import { MetricsController } from './metrics.controller.js';
import { MetricsService } from './metrics.service.js';

@Module({
  controllers: [MetricsController],
  providers: [MetricsService],
})
export class MetricsModule implements NestModule {
  configure(consumer: MiddlewareConsumer) {
    consumer
      .apply(HttpMetricsMiddleware)
      .exclude('metrics', 'health/live', 'health/ready')
      .forRoutes('{*path}');
  }
}
