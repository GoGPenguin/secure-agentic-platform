import { Controller, Get, Inject, Res } from '@nestjs/common';
import type { Response } from 'express';
import { MetricsService } from './metrics.service.js';

@Controller('metrics')
export class MetricsController {
  constructor(
    @Inject(MetricsService) private readonly metrics: MetricsService,
  ) {}

  @Get()
  async getMetrics(@Res() res: Response) {
    res.type(this.metrics.registry.contentType);
    res.send(await this.metrics.registry.metrics());
  }
}
