import { api } from "../../services/api";
import { runtimeConfig } from "../../config";
import { visiblePage } from "../../services/pagination.js";
import {
  filterProductSpecs,
  filterProjectMembers,
  filterRaciRows,
  hasLongSpecContent,
} from "../../services/project-review-filter.js";
import type { ProductSpec, ProjectMember, ProjectReview } from "../../types";

type ReviewTab = "specs" | "members" | "raci";

interface TabTapEvent {
  currentTarget: { dataset: { tab: ReviewTab } };
}

interface SearchInputEvent { detail: { value: string } }
interface SpecTapEvent { currentTarget: { dataset: { row: number } } }

interface SpecView extends ProductSpec {
  detail: string;
  expandable: boolean;
  expanded: boolean;
}

interface RaciView {
  code: string;
  name: string;
  output: string;
  roles: Array<{ key: "R" | "A" | "C" | "I"; names: string }>;
}

const valueOrEmpty = (value: string | null) => value?.trim() || "";

Page({
  data: {
    projectId: "",
    review: null as ProjectReview | null,
    specs: [] as SpecView[],
    filteredSpecs: [] as SpecView[],
    visibleSpecs: [] as SpecView[],
    specKeyword: "",
    members: [] as ProjectMember[],
    filteredMembers: [] as ProjectMember[],
    memberKeyword: "",
    raciRows: [] as RaciView[],
    filteredRaciRows: [] as RaciView[],
    visibleRaciRows: [] as RaciView[],
    raciKeyword: "",
    specPage: 1,
    raciPage: 1,
    activeTab: "specs" as ReviewTab,
    loading: true,
    loadError: false,
  },
  async onLoad(options: Record<string, string | undefined>) {
    const projectId = options.projectId || wx.getStorageSync<string>("current_project_id");
    this.setData({ projectId });
    await this.loadReview();
  },
  async loadReview() {
    const projectId = this.data.projectId;
    this.setData({ loading: true, loadError: false });
    try {
      const review = await api.projectReview(projectId);
      const specs = review.product_specs.map((spec) => {
        const detail = [spec.configuration, spec.core_information, spec.selected_model]
          .map(valueOrEmpty)
          .filter(Boolean)
          .join(" · ") || "—";
        return {
          ...spec,
          detail,
          expandable: hasLongSpecContent(
            { detail, notes: spec.notes },
            runtimeConfig.projectReviewCollapseLength,
          ),
          expanded: false,
        };
      });
      const raciRows = review.milestones.map((milestone) => ({
        code: milestone.code,
        name: milestone.name,
        output: milestone.output || "—",
        roles: (["R", "A", "C", "I"] as const).map((key) => ({
          key,
          names: milestone.assignments[key]?.join("、") || "—",
        })),
      }));
      this.setData({
        review,
        specs,
        filteredSpecs: specs,
        visibleSpecs: visiblePage(specs, 1, runtimeConfig.projectReviewPageSize),
        members: review.members,
        filteredMembers: review.members,
        raciRows,
        filteredRaciRows: raciRows,
        visibleRaciRows: visiblePage(raciRows, 1, runtimeConfig.projectReviewPageSize),
        specPage: 1,
        raciPage: 1,
        loadError: false,
      });
    } catch {
      this.setData({ loadError: true });
    } finally {
      this.setData({ loading: false });
    }
  },
  selectTab(event: TabTapEvent) {
    this.setData({ activeTab: event.currentTarget.dataset.tab });
  },
  onSpecKeywordInput(event: SearchInputEvent) {
    const specKeyword = event.detail.value;
    const filteredSpecs = filterProductSpecs(this.data.specs, specKeyword);
    this.setData({
      specKeyword,
      filteredSpecs,
      visibleSpecs: visiblePage(filteredSpecs, 1, runtimeConfig.projectReviewPageSize),
      specPage: 1,
    });
  },
  clearSpecKeyword() {
    const filteredSpecs = this.data.specs;
    this.setData({
      specKeyword: "",
      filteredSpecs,
      visibleSpecs: visiblePage(filteredSpecs, 1, runtimeConfig.projectReviewPageSize),
      specPage: 1,
    });
  },
  toggleSpecDetail(event: SpecTapEvent) {
    const rowNumber = event.currentTarget.dataset.row;
    const specs = this.data.specs.map((spec) => spec.row_number === rowNumber
      ? { ...spec, expanded: !spec.expanded }
      : spec);
    const filteredSpecs = filterProductSpecs(specs, this.data.specKeyword);
    this.setData({
      specs,
      filteredSpecs,
      visibleSpecs: visiblePage(
        filteredSpecs,
        this.data.specPage,
        runtimeConfig.projectReviewPageSize,
      ),
    });
  },
  onMemberKeywordInput(event: SearchInputEvent) {
    const memberKeyword = event.detail.value;
    this.setData({
      memberKeyword,
      filteredMembers: filterProjectMembers(this.data.members, memberKeyword),
    });
  },
  clearMemberKeyword() {
    this.setData({ memberKeyword: "", filteredMembers: this.data.members });
  },
  onRaciKeywordInput(event: SearchInputEvent) {
    const raciKeyword = event.detail.value;
    const filteredRaciRows = filterRaciRows(this.data.raciRows, raciKeyword);
    this.setData({
      raciKeyword,
      filteredRaciRows,
      visibleRaciRows: visiblePage(filteredRaciRows, 1, runtimeConfig.projectReviewPageSize),
      raciPage: 1,
    });
  },
  clearRaciKeyword() {
    const filteredRaciRows = this.data.raciRows;
    this.setData({
      raciKeyword: "",
      filteredRaciRows,
      visibleRaciRows: visiblePage(filteredRaciRows, 1, runtimeConfig.projectReviewPageSize),
      raciPage: 1,
    });
  },
  showMoreSpecs() {
    const specPage = this.data.specPage + 1;
    this.setData({
      specPage,
      visibleSpecs: visiblePage(
        this.data.filteredSpecs,
        specPage,
        runtimeConfig.projectReviewPageSize,
      ),
    });
  },
  showMoreRaci() {
    const raciPage = this.data.raciPage + 1;
    this.setData({
      raciPage,
      visibleRaciRows: visiblePage(
        this.data.filteredRaciRows,
        raciPage,
        runtimeConfig.projectReviewPageSize,
      ),
    });
  },
});
