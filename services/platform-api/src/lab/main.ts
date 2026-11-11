import { NestFactory } from '@nestjs/core';
import { LabAppModule } from './lab-app.module.js';

const app = await NestFactory.create(LabAppModule.register());
await app.listen(process.env.PORT ?? 3000);
