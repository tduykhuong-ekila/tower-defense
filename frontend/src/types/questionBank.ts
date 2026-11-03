export interface QuestionBankPreview {
  id: string;
  upload_token?: string;
  source_filename: string;
  valid_questions: number;
  invalid_questions: number;
  status: 'VALIDATED' | 'INVALID' | 'ATTACHED' | 'EXPIRED';
  can_create: boolean;
  errors: { sheet: string; row: number; field: string; message: string }[];
  sheets: string[];
  page: number;
  page_size: number;
  questions: {
    id: string; content: string; import_order: number; answer_key: string;
    options: { key: string; text: string }[];
    import_metadata: { sheet: string; row: number; STT: number };
  }[];
}

export interface StagedQuestionBank { id: string; token: string }
