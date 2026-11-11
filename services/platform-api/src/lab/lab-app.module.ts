import { Module, type DynamicModule } from '@nestjs/common';
import { AppModule } from '../app.module.js';
import { labHttp503Enabled } from '../config/lab-http-503.js';
import { Http503Controller } from './http-503.controller.js';

@Module({})
export class LabAppModule {
  static register(env: NodeJS.ProcessEnv = process.env): DynamicModule {
    return {
      module: LabAppModule,
      imports: [AppModule],
      controllers: labHttp503Enabled(env) ? [Http503Controller] : [],
    };
  }
}
