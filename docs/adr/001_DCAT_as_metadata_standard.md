# ADR 001: DCAT을 메타데이터 표준으로 채택

> **Date:** 2026-07-01
> **Status:** Accepted

---

## 배경

다양한 데이터 소스(Naver, YouTube, 뉴스 등)에 대해 공통 메타데이터 스키마가 필요했다.

## 결정

W3C DCAT 2 (Data Catalog Vocabulary)를 메타데이터 표준으로 채택한다.

## 이유

- W3C 표준 — 외부 카탈로그 시스템과 연동 가능
- 데이터 소스 종류에 무관하게 공통 스키마 적용 가능
- `dct:license`, `dcat:landingPage` 등 필요한 필드가 이미 정의되어 있음
- PROV-O(출처 온톨로지)와 자연스럽게 연계됨

## 비표준 확장

DCAT에 없는 운영 목적 필드는 `(확장)` 주석으로 표시하고 별도 테이블(`data_registry`)에 분리한다.
