import { Controller, Get } from '@nestjs/common';
import { InfoService } from './info.service.js';

@Controller('api/v1/info')
export class InfoController {
  constructor(private readonly infoService: InfoService) {}

  @Get()
  getInfo(): { service: string; version: string } {
    return this.infoService.getInfo();
  }
}
