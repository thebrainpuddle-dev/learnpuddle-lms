// src/services/reportBuilderService.test.ts
//
// Unit tests for the Report Builder service wrapper. We stub out the `api`
// axios instance and assert URL + payload shape + response shape for every
// exported helper.

import {
  reportBuilderService,
  normaliseGroupBy,
  serialiseGroupBy,
  type ReportDefinition,
  type ReportScheduleWritePayload,
} from './reportBuilderService';
import api from '../config/api';

vi.mock('../config/api', () => ({
  __esModule: true,
  default: {
    get: vi.fn(),
    post: vi.fn(),
    patch: vi.fn(),
    delete: vi.fn(),
  },
}));

const mockedApi = api as unknown as {
  get: ReturnType<typeof vi.fn>;
  post: ReturnType<typeof vi.fn>;
  patch: ReturnType<typeof vi.fn>;
  delete: ReturnType<typeof vi.fn>;
};

const FIXTURE_DEFINITION: ReportDefinition = {
  id: 'def-1',
  name: 'Teachers',
  description: 'All teachers',
  data_source: 'teacher_progress',
  created_by: 'u-1',
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-02T00:00:00Z',
  filters_json: [],
  group_by_json: [],
  aggregates_json: [],
  is_soft_deleted: false,
};

describe('reportBuilderService', () => {
  beforeEach(() => vi.resetAllMocks());

  it('getSchema calls /v1/admin/reports/schema/', async () => {
    mockedApi.get.mockResolvedValue({
      data: {
        data_sources: [
          {
            name: 'teacher_progress',
            label: 'Teacher Progress',
            fields: ['id', 'teacher_id'],
            operators: ['eq', 'in'],
            aggregates: ['count', 'avg'],
          },
        ],
      },
    });
    const res = await reportBuilderService.getSchema();
    expect(mockedApi.get).toHaveBeenCalledWith('/v1/admin/reports/schema/');
    expect(res.data_sources).toHaveLength(1);
    expect(res.data_sources[0].name).toBe('teacher_progress');
  });

  it('listDefinitions calls /v1/admin/reports/definitions/', async () => {
    mockedApi.get.mockResolvedValue({ data: [] });
    await reportBuilderService.listDefinitions();
    expect(mockedApi.get).toHaveBeenCalledWith('/v1/admin/reports/definitions/');
  });

  it('getDefinition returns the fetched definition by id', async () => {
    mockedApi.get.mockResolvedValue({ data: FIXTURE_DEFINITION });
    const res = await reportBuilderService.getDefinition('def-1');
    expect(mockedApi.get).toHaveBeenCalledWith(
      '/v1/admin/reports/definitions/def-1/',
    );
    expect(res.id).toBe('def-1');
  });

  it('createDefinition POSTs the payload', async () => {
    mockedApi.post.mockResolvedValue({ data: FIXTURE_DEFINITION });
    await reportBuilderService.createDefinition({
      name: 'X',
      data_source: 'teacher_progress',
      filters_json: [],
      group_by_json: [],
      aggregates_json: [],
    });
    expect(mockedApi.post).toHaveBeenCalledWith(
      '/v1/admin/reports/definitions/',
      expect.objectContaining({ name: 'X' }),
    );
  });

  it('updateDefinition PATCHes by id', async () => {
    mockedApi.patch.mockResolvedValue({ data: FIXTURE_DEFINITION });
    await reportBuilderService.updateDefinition('def-1', { name: 'New' });
    expect(mockedApi.patch).toHaveBeenCalledWith(
      '/v1/admin/reports/definitions/def-1/',
      { name: 'New' },
    );
  });

  it('deleteDefinition DELETEs by id', async () => {
    mockedApi.delete.mockResolvedValue({ data: null });
    await reportBuilderService.deleteDefinition('def-1');
    expect(mockedApi.delete).toHaveBeenCalledWith(
      '/v1/admin/reports/definitions/def-1/',
    );
  });

  it('runDefinition POSTs to /run/ and returns the run result', async () => {
    mockedApi.post.mockResolvedValue({
      data: { run_id: 'r-1', row_count: 2, rows: [{ a: 1 }, { a: 2 }] },
    });
    const res = await reportBuilderService.runDefinition('def-1');
    expect(mockedApi.post).toHaveBeenCalledWith(
      '/v1/admin/reports/definitions/def-1/run/',
    );
    expect(res.row_count).toBe(2);
  });

  it('runDefinition surfaces ROW_CAP_EXCEEDED via rejected promise', async () => {
    mockedApi.post.mockRejectedValue({
      response: { status: 400, data: { error: 'ROW_CAP_EXCEEDED' } },
    });
    await expect(reportBuilderService.runDefinition('def-1')).rejects.toMatchObject(
      { response: { data: { error: 'ROW_CAP_EXCEEDED' } } },
    );
  });

  it('exportDefinition POSTs to /export/', async () => {
    mockedApi.post.mockResolvedValue({ data: { run_id: 'r-1' } });
    const res = await reportBuilderService.exportDefinition('def-1');
    expect(mockedApi.post).toHaveBeenCalledWith(
      '/v1/admin/reports/definitions/def-1/export/',
    );
    expect(res.run_id).toBe('r-1');
  });

  it('listRuns passes definition_id as query param when provided', async () => {
    mockedApi.get.mockResolvedValue({ data: [] });
    await reportBuilderService.listRuns('def-1');
    expect(mockedApi.get).toHaveBeenCalledWith('/v1/admin/reports/runs/', {
      params: { definition_id: 'def-1' },
    });
  });

  it('getDownloadUrl calls runs/{id}/download/', async () => {
    mockedApi.get.mockResolvedValue({
      data: { download_url: 'https://x/y.csv', expires_in: 600 },
    });
    const res = await reportBuilderService.getDownloadUrl('r-1');
    expect(mockedApi.get).toHaveBeenCalledWith(
      '/v1/admin/reports/runs/r-1/download/',
    );
    expect(res.download_url).toBe('https://x/y.csv');
  });

  it('createSchedule POSTs schedule payload under the definition', async () => {
    const payload: ReportScheduleWritePayload = {
      cadence: 'weekly',
      run_at_hour: 6,
      run_at_day_of_week: 1,
      recipients_json: ['a@b.com'],
      enabled: true,
    };
    mockedApi.post.mockResolvedValue({ data: { id: 's-1', ...payload } });
    await reportBuilderService.createSchedule('def-1', payload);
    expect(mockedApi.post).toHaveBeenCalledWith(
      '/v1/admin/reports/definitions/def-1/schedules/',
      payload,
    );
  });

  it('updateSchedule PATCHes and deleteSchedule DELETEs by schedule id', async () => {
    mockedApi.patch.mockResolvedValue({ data: { id: 's-1' } });
    mockedApi.delete.mockResolvedValue({ data: null });
    await reportBuilderService.updateSchedule('def-1', 's-1', { enabled: false });
    expect(mockedApi.patch).toHaveBeenCalledWith(
      '/v1/admin/reports/definitions/def-1/schedules/s-1/',
      { enabled: false },
    );
    await reportBuilderService.deleteSchedule('def-1', 's-1');
    expect(mockedApi.delete).toHaveBeenCalledWith(
      '/v1/admin/reports/definitions/def-1/schedules/s-1/',
    );
  });

  it('normaliseGroupBy handles both wire formats', () => {
    expect(normaliseGroupBy(['a', 'b'])).toEqual([{ field: 'a' }, { field: 'b' }]);
    expect(
      normaliseGroupBy([{ field: 'x' }, { field: 'y' }]),
    ).toEqual([{ field: 'x' }, { field: 'y' }]);
    expect(normaliseGroupBy(null)).toEqual([]);
    expect(normaliseGroupBy(undefined)).toEqual([]);
  });

  it('serialiseGroupBy flattens to string[]', () => {
    expect(serialiseGroupBy([{ field: 'a' }, { field: 'b' }])).toEqual(['a', 'b']);
  });
});
