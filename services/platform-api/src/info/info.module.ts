import { Module } from '@nestjs/common';
import { InfoController } from './info.controller.js';
import { InfoService } from './info.service.js';

@Module({
  controllers: [InfoController],
  providers: [InfoService],
})
export class InfoModule {}
