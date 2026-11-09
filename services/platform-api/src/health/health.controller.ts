import { Controller, Get } from '@nestjs/common';

@Controller('health')
export class HealthController {
  @Get('live')
  live(): { status: string } {
    return { status: 'ok' };
  }

  // There are no dependencies to check; serving requests implies readiness.
  @Get('ready')
  ready(): { status: string } {
    return { status: 'ready' };
  }
}
