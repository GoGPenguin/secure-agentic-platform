import { NestFactory } from '@nestjs/core';
import { AppModule } from './app.module.js';
import { validateProductionEnvironment } from './config/lab-http-503.js';

async function bootstrap() {
  validateProductionEnvironment(process.env);
  const app = await NestFactory.create(AppModule);
  await app.listen(process.env.PORT ?? 3000);
}
await bootstrap();
