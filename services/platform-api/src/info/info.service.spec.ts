import { Test } from '@nestjs/testing';
import { InfoService } from './info.service.js';

describe('InfoService', () => {
  it('returns the platform service name and version', async () => {
    const module = await Test.createTestingModule({
      providers: [InfoService],
    }).compile();

    try {
      expect(module.get(InfoService).getInfo()).toEqual({
        service: 'platform-api',
        version: '0.1.1',
      });
    } finally {
      await module.close();
    }
  });
});
