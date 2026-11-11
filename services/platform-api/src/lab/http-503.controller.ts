import { Controller, Post, ServiceUnavailableException } from '@nestjs/common';

@Controller('api/v1/lab/failures')
export class Http503Controller {
  @Post('http-503')
  fail(): never {
    throw new ServiceUnavailableException('Controlled lab HTTP 503');
  }
}
