import { Injectable } from '@nestjs/common';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const { name, version } = require('../../package.json') as {
  name: string;
  version: string;
};

@Injectable()
export class InfoService {
  getInfo(): { service: string; version: string } {
    return { service: name, version };
  }
}
